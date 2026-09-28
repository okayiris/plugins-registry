#!/usr/bin/env python3
"""Google Ads for Iris: read campaigns, spend and reports. Read-only.

  ads                          what is set up, and what still needs a link
  ads setup                    one-time: OAuth client, the client secret in the vault, the developer token
  ads login                    print the one-time OAuth link
  ads login --code <url|code>  finish the OAuth login with the address you were sent to
  ads accounts                 the customers this login may read
  ads customer <id>            choose the Google Ads customer id (hyphens are fine)
  ads manager <id>             optional manager (MCC) id, sent as login-customer-id
  ads campaigns [--days N]     campaigns with status, budget and metrics (default 30 days)
  ads costs [--days N] [--by day|campaign]   spend, by day or by campaign
  ads report "<GAQL query>"    run any read-only Google Ads Query Language query
  ads version [vNN]            show or set the API version (default v25)

This plugin only reads. It never calls a mutate method and never changes a campaign, budget or bid.

The OAuth client secret lives in the vault and is used only by the vault during the login and token
refresh (kluis doe), so this tool never sees it. The developer token and the short-lived OAuth tokens
are kept in .state.json next to this file (mode 600, readable only by the owner) and are never printed;
see README.md for why the developer token cannot go through the vault.
"""

import getpass
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / ".state.json"
CONFIG = HERE / "config.json"

VAULT_ITEM = "google-ads-oauth"
VAULT_DOMAIN = "googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/adwords"
# A loopback address: Google allows it for Desktop-app clients without registering the exact port. The
# browser cannot reach this house, so the page fails to load and you copy the code out of the address bar.
REDIRECT = "http://127.0.0.1:8765/callback"
DEFAULT_VERSION = "v25"
API_HOST = "https://googleads.googleapis.com"


def fail(text):
    print(f"ads: {text}")
    sys.exit(1)


# ---------------------------------------------------------------- state and config

def load_json(path, fallback):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else fallback
    except (OSError, ValueError):
        return fallback


def state():
    return load_json(STATE, {})


def config():
    return load_json(CONFIG, {})


def save_state(update):
    data = state()
    data.update(update)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(tmp, STATE)


def api_version():
    value = str(state().get("api_version") or config().get("api_version") or DEFAULT_VERSION).strip()
    if not value.startswith("v"):
        value = "v" + value
    return value


def client_id():
    return str(state().get("client_id") or config().get("client_id") or "").strip()


def developer_token():
    return str(os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN") or state().get("developer_token") or "").strip()


def customer_id():
    return str(state().get("customer_id") or "").strip()


def manager_id():
    return str(state().get("login_customer_id") or "").strip()


def norm_customer(value):
    """A Google Ads customer id is ten digits, with or without hyphens."""
    if not value:
        return ""
    value = str(value).strip()
    if value.startswith("customers/"):
        value = value.split("/", 1)[1]
    digits = "".join(c for c in value if c.isdigit())
    return digits


def require_customer():
    cid = customer_id()
    if not cid:
        fail("no Google Ads customer id chosen yet. Run `ads accounts`, then `ads customer <id>`.")
    return cid


# ---------------------------------------------------------------- the vault

def vault_bin():
    path = shutil.which("kluis") or shutil.which("vault")
    if path:
        return path
    local = Path.home() / ".local" / "bin" / "kluis"
    return str(local) if local.is_file() else None


def vault_items():
    exe = vault_bin()
    if not exe:
        return []
    try:
        proc = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    out = (proc.stdout or "").strip()
    if not out or "leeg" in out.lower() or "empty" in out.lower():
        return []
    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        names.append(line.split("  ")[0].strip())
    return names


def vault_has(item):
    return item in vault_items()


def vault_ask(item, explanation):
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not available in this house")
    print("A window opens so you can paste the value; Iris never sees it.")
    try:
        proc = subprocess.run(
            [exe, "vraag", item, "--domein", VAULT_DOMAIN, explanation],
            capture_output=True, text=True, timeout=200)
    except (OSError, subprocess.TimeoutExpired):
        fail("the vault did not answer")
    if proc.returncode != 0:
        fail((proc.stderr or proc.stdout or "the vault refused").strip())


def vault_call(method, url, body=None, header=None):
    """Let the vault make the call, with {g} replaced by the stored client secret. Never returns a secret."""
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not available; the OAuth client secret is needed")
    cmd = [exe, "doe", VAULT_ITEM, method, url]
    if body is not None:
        cmd.append(body)
    if header:
        cmd += ["--kop", header]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        fail("the vault did not answer in time")
    except OSError as exc:
        fail(f"cannot reach the vault ({exc})")
    out = (proc.stdout or "").strip()
    first, _, rest = out.partition("\n")
    status = None
    if first.startswith("status "):
        try:
            status = int(first.split()[1])
        except (IndexError, ValueError):
            pass
    if status is None:
        fail((proc.stderr or out or "the vault refused the call").strip())
    return status, rest.strip()


def vault_do_token(pairs):
    """Exchange at Google's token endpoint through the vault. The client secret is the vault secret."""
    body = urllib.parse.urlencode(pairs)
    status, text = vault_call("POST", TOKEN_URL, body=body,
                              header="Content-Type: application/x-www-form-urlencoded")
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    if status != 200 or not data.get("access_token"):
        message = data.get("error_description") or data.get("error") or text or f"status {status}"
        fail(f"Google refused the token exchange: {message}")
    return data


# ---------------------------------------------------------------- OAuth

def oauth_url():
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id(),
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    })


def token_exchange(pairs):
    data = vault_do_token(pairs)
    update = {
        "access_token": data["access_token"],
        "expires_at": int(time.time()) + int(data.get("expires_in", 3600)),
    }
    if data.get("refresh_token"):
        update["refresh_token"] = data["refresh_token"]
    save_state(update)
    return data


def access_token():
    tokens = state()
    now = int(time.time())
    if tokens.get("access_token") and int(tokens.get("expires_at", 0)) > now + 60:
        return tokens["access_token"]
    if not tokens.get("refresh_token"):
        fail("not logged in yet. Run `ads login`, open the link and finish with `ads login --code <url>`.")
    if not vault_has(VAULT_ITEM):
        fail(f'the OAuth client secret is not in the vault (looked for "{VAULT_ITEM}"). '
             f'Run: kluis vraag {VAULT_ITEM} --domein {VAULT_DOMAIN} "Google Ads OAuth client secret"')
    data = vault_do_token([
        ("grant_type", "refresh_token"),
        ("refresh_token", tokens["refresh_token"]),
        ("client_id", client_id()),
        ("client_secret", "{g}"),
    ])
    save_state({
        "access_token": data["access_token"],
        "expires_at": now + int(data.get("expires_in", 3600)),
        "refresh_token": data.get("refresh_token", tokens["refresh_token"]),
    })
    return data["access_token"]


# ---------------------------------------------------------------- HTTP to Google Ads

def http_json(method, url, token, body=None, login_customer=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "developer-token": developer_token(),
        "Accept": "application/json",
    }
    if login_customer:
        headers["login-customer-id"] = login_customer
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"error": {"message": raw[:300]}}
    except OSError as exc:
        fail(f"Google Ads is unreachable ({exc})")


def api_error(status, data):
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, list) and error:
        error = error[0]
    if not isinstance(error, dict):
        return f"Google Ads returned status {status}."
    message = (error.get("message") or "unknown error").strip().rstrip(".")
    reason = ""
    for detail in error.get("details") or []:
        for item in detail.get("errors") or []:
            codes = item.get("errorCode") or {}
            for value in codes.values():
                reason = value
                break
            if item.get("message"):
                message = item["message"].strip().rstrip(".")
            break
    if status == 401:
        return ("Google Ads says the login is not valid (401). If this keeps happening, run "
                "`ads login` again to refresh the OAuth tokens.")
    if status == 403:
        if "developer" in message.lower() or reason.startswith("DEVELOPER_TOKEN"):
            return (f"Google Ads refused the developer token (403): {message}. Check the token in the "
                    "Google Ads API Center and that your account has API access.")
        return f"Google Ads refused the request (403): {message}."
    if status == 400:
        return f"Google Ads rejected the query (400): {message}."
    if status == 404:
        return (f"Google Ads could not find that customer (404): {message}. Check the customer id and, "
                "with a manager account, the login-customer-id.")
    if status == 429:
        return "Google Ads rate limit reached (429). Try again in a moment."
    return f"Google Ads returned {status}: {message}" + (f" ({reason})" if reason else "")


def require_ready():
    token = developer_token()
    if not token:
        fail("no developer token yet. Run `ads setup` (it stores the token hidden, mode 600, in .state.json).")
    if not client_id():
        fail("no OAuth client id yet. Run `ads setup`.")
    return access_token()


def search_stream(query, customer=None):
    cid = norm_customer(customer or require_customer())
    token = require_ready()
    url = f"{API_HOST}/{api_version()}/customers/{cid}/googleAds:searchStream"
    status, data = http_json("POST", url, token, body={"query": query}, login_customer=manager_id() or None)
    if status >= 400:
        fail(api_error(status, data))
    batches = data if isinstance(data, list) else [data]
    rows = []
    for batch in batches:
        if isinstance(batch, dict) and batch.get("error"):
            fail(api_error(status, batch))
        rows.extend(batch.get("results", []) if isinstance(batch, dict) else [])
    return rows


def customer_info(cid):
    rows = search_stream("SELECT customer.id, customer.descriptive_name, customer.currency_code, "
                         "customer.time_zone FROM customer LIMIT 1", customer=cid)
    if not rows:
        return {}
    return rows[0].get("customer", {})


# ---------------------------------------------------------------- formatting

def money(micros, currency=""):
    try:
        amount = int(micros) / 1_000_000
    except (TypeError, ValueError):
        amount = 0.0
    text = f"{amount:,.2f}"
    return f"{text} {currency}".strip()


def whole(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def ratio(value):
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def date_range(days):
    end = date.today()
    start = end - timedelta(days=max(1, days) - 1)
    return start.isoformat(), end.isoformat()


def parse_days(args, opts):
    value = opts.get("days")
    if value is None:
        return 30
    try:
        days = int(value)
    except ValueError:
        fail("--days needs a number, for example --days 7")
    return max(1, min(days, 366))


# ---------------------------------------------------------------- commands

def cmd_status():
    st = state()
    print("Google Ads, read-only: campaigns, spend and reports.")
    print(f"API version: {api_version()}")
    missing = []
    if not client_id():
        missing.append("OAuth client id (desktop app)")
    if not vault_has(VAULT_ITEM):
        missing.append(f'OAuth client secret in the vault ("{VAULT_ITEM}")')
    if not developer_token():
        missing.append("developer token")
    if not st.get("refresh_token"):
        missing.append("login (OAuth refresh token)")
    if not customer_id():
        missing.append("customer id")
    if missing:
        print()
        print("Not set up yet. Still missing: " + ", ".join(missing) + ".")
        print("Run `ads setup`, then `ads login`, then choose a customer with `ads customer <id>`.")
        print("See README.md for the developer token and the OAuth client from your own Google projects.")
        return
    cid = customer_id()
    name = st.get("customer_name") or ""
    currency = st.get("currency") or ""
    print(f"Customer: {cid}" + (f" ({name})" if name else "")
          + (f", currency {currency}" if currency else ""))
    if manager_id():
        print(f"Login-customer-id (manager): {manager_id()}")
    print("Ready. Try: ads campaigns --days 30, ads costs --days 7, ads report \"SELECT ...\"")


def cmd_setup(args, opts):
    cid = opts.get("client-id") or client_id()
    if not cid:
        try:
            cid = input("OAuth client id (Desktop app): ").strip()
        except EOFError:
            cid = ""
    if not cid:
        fail("an OAuth client id is needed. Create a Desktop app in Google Cloud and run "
             "`ads setup --client-id <id>`.")
    save_state({"client_id": cid})
    if opts.get("api-version"):
        save_state({"api_version": str(opts["api-version"])})
    if not vault_has(VAULT_ITEM):
        vault_ask(VAULT_ITEM, "Google Ads OAuth client secret (Desktop app)")
    elif not opts.get("quiet"):
        print(f'The client secret is already in the vault as "{VAULT_ITEM}".')
    if not developer_token():
        env = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
        if env:
            save_state({"developer_token": env.strip()})
        else:
            print("Paste your Google Ads developer token (input hidden; it is stored in .state.json, "
                  "mode 600, and never printed):")
            try:
                token = getpass.getpass("Developer token: ").strip()
            except EOFError:
                token = ""
            if not token:
                fail("no developer token given. Get one in the Google Ads API Center of your manager "
                     "account, then run `ads setup` again.")
            save_state({"developer_token": token})
    print()
    print("Saved. Now run `ads login` to connect your Google account.")
    print("If you use a manager (MCC) account, set it later with `ads manager <id>`.")


def cmd_login(args, opts):
    if not client_id():
        fail("no OAuth client id yet. Run `ads setup` first.")
    if not vault_has(VAULT_ITEM):
        fail(f'the OAuth client secret is not in the vault (looked for "{VAULT_ITEM}"). Run `ads setup`.')
    code = opts.get("code")
    if not code:
        print("Open this link, sign in and allow access. You land on an address that does not load;")
        print("that is expected. Copy the whole address bar and run `ads login --code \"<that address>\"`.")
        print()
        print(oauth_url())
        return
    if "code=" in code:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    if not code:
        fail("I could not find a code in that address. Copy the whole address bar you landed on.")
    token_exchange([
        ("grant_type", "authorization_code"),
        ("code", code),
        ("redirect_uri", REDIRECT),
        ("client_id", client_id()),
        ("client_secret", "{g}"),
    ])
    print("Logged in. The tokens are stored in .state.json (mode 600) and are never printed.")
    print("Next: `ads accounts` to see the customers, then `ads customer <id>`.")


def cmd_accounts():
    if not state().get("refresh_token"):
        fail("not logged in yet. Run `ads login` first.")
    token = require_ready()
    url = f"{API_HOST}/{api_version()}/customers:listAccessibleCustomers"
    status, data = http_json("GET", url, token, login_customer=manager_id() or None)
    if status >= 400:
        fail(api_error(status, data))
    names = data.get("resourceNames") or []
    if not names:
        print("This login can read no Google Ads customers. Check that your user has access and, for a "
              "manager account, set it with `ads manager <id>`.")
        return
    for resource in names:
        cid = norm_customer(resource)
        info = customer_info(cid)
        label = f"{cid}"
        if info.get("descriptiveName"):
            label += f"  {info['descriptiveName']}"
        if info.get("currencyCode"):
            label += f"  ({info['currencyCode']})"
        print(label)
    print()
    print("Choose one with: ads customer <id>")


def cmd_customer(args, opts):
    value = args[0] if args else opts.get("id")
    cid = norm_customer(value)
    if not cid:
        fail("use: ads customer <id> (ten digits; hyphens are fine)")
    save_state({"customer_id": cid})
    print(f"Customer set to {cid}.")
    info = {}
    if state().get("refresh_token") and developer_token() and client_id():
        info = customer_info(cid)
    if info:
        save_state({
            "customer_name": info.get("descriptiveName", ""),
            "currency": info.get("currencyCode", ""),
            "time_zone": info.get("timeZone", ""),
        })
        name = info.get("descriptiveName") or "?"
        currency = info.get("currencyCode") or "?"
        print(f"{name}, currency {currency}.")


def cmd_manager(args, opts):
    value = args[0] if args else opts.get("id")
    cid = norm_customer(value)
    if not cid:
        fail("use: ads manager <id> (the manager/MCC account id; hyphens are fine)")
    save_state({"login_customer_id": cid})
    print(f"Login-customer-id set to {cid}.")


def cmd_version(args, opts):
    value = args[0] if args else None
    if not value:
        print(f"API version: {api_version()}")
        return
    value = str(value).strip()
    if not value.startswith("v") or not value[1:].isdigit():
        fail("use a version like v25")
    save_state({"api_version": value})
    print(f"API version set to {value}.")


def cmd_campaigns(args, opts):
    days = parse_days(args, opts)
    start, end = date_range(days)
    cid = require_customer()
    info = customer_info(cid)
    currency = info.get("currencyCode") or state().get("currency") or ""
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign.advertising_channel_type,
          campaign_budget.amount_micros,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.ctr,
          metrics.average_cpc
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.status != 'REMOVED'
        ORDER BY metrics.cost_micros DESC
    """
    rows = search_stream(query, customer=cid)
    print(f"Campaigns {start} to {end}" + (f" ({currency})" if currency else ""))
    if not rows:
        print("No campaigns with activity in this period.")
        return
    for row in rows:
        campaign = row.get("campaign", {})
        metrics = row.get("metrics", {})
        budget = row.get("campaignBudget", {}).get("amountMicros")
        status = campaign.get("status", "?")
        channel = campaign.get("advertisingChannelType", "")
        print()
        print(f"{campaign.get('name', '?')}  [{status}{', ' + channel if channel else ''}]")
        print(f"  spend {money(metrics.get('costMicros'), currency)}   "
              f"clicks {whole(metrics.get('clicks'))}   "
              f"impr. {whole(metrics.get('impressions'))}   "
              f"ctr {ratio(metrics.get('ctr'))}   "
              f"avg cpc {money(metrics.get('averageCpc'), currency)}")
        if budget not in (None, "0", 0):
            print(f"  budget {money(budget, currency)} (total)")


def cmd_costs(args, opts):
    days = parse_days(args, opts)
    by = (opts.get("by") or "day").strip().lower()
    if by not in ("day", "campaign"):
        fail("--by takes day or campaign")
    start, end = date_range(days)
    cid = require_customer()
    info = customer_info(cid)
    currency = info.get("currencyCode") or state().get("currency") or ""
    if by == "day":
        query = f"""
            SELECT segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks,
                   metrics.conversions
            FROM campaign
            WHERE segments.date BETWEEN '{start}' AND '{end}'
            ORDER BY segments.date DESC
        """
        rows = search_stream(query, customer=cid)
        totals = {}
        for row in rows:
            day = row.get("segments", {}).get("date", "?")
            bucket = totals.setdefault(day, {"cost": 0, "clicks": 0, "impr": 0, "conv": 0.0})
            metrics = row.get("metrics", {})
            bucket["cost"] += int(metrics.get("costMicros", 0) or 0)
            bucket["clicks"] += int(metrics.get("clicks", 0) or 0)
            bucket["impr"] += int(metrics.get("impressions", 0) or 0)
            bucket["conv"] += float(metrics.get("conversions", 0) or 0)
        print(f"Spend by day, {start} to {end}" + (f" ({currency})" if currency else ""))
        if not totals:
            print("No spend in this period.")
            return
        grand = 0
        for day in sorted(totals, reverse=True):
            bucket = totals[day]
            grand += bucket["cost"]
            print(f"{day}  {money(bucket['cost'], currency):>14}   "
                  f"clicks {whole(bucket['clicks']):>8}   impr. {whole(bucket['impr']):>10}")
        print(f"total  {money(grand, currency)}")
        return
    query = f"""
        SELECT campaign.id, campaign.name, metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        ORDER BY metrics.cost_micros DESC
    """
    rows = search_stream(query, customer=cid)
    print(f"Spend by campaign, {start} to {end}" + (f" ({currency})" if currency else ""))
    if not rows:
        print("No spend in this period.")
        return
    total = 0
    for row in rows:
        campaign = row.get("campaign", {})
        metrics = row.get("metrics", {})
        total += int(metrics.get("costMicros", 0) or 0)
        print(f"{money(metrics.get('costMicros'), currency):>14}   "
              f"clicks {whole(metrics.get('clicks')):>8}   "
              f"impr. {whole(metrics.get('impressions')):>10}   {campaign.get('name', '?')}")
    print(f"total  {money(total, currency)}")


def cmd_report(args, opts):
    query = opts.get("query") or (" ".join(args) if args else "")
    query = query.strip()
    if not query:
        fail('use: ads report "SELECT campaign.id, metrics.cost_micros FROM campaign ..."')
    first = query.lstrip().split(None, 1)[0].upper() if query.strip() else ""
    if first != "SELECT":
        fail("this plugin is read-only: a report must start with SELECT.")
    rows = search_stream(query)
    if not rows:
        print("The report returned no rows.")
        return
    flattened = []
    for row in rows:
        flat = {}
        flatten(row, "", flat)
        flattened.append(flat)
    keys = []
    for flat in flattened:
        for key in flat:
            if key not in keys:
                keys.append(key)
    widths = {key: min(max(len(key), *(len(str(f.get(key, ""))) for f in flattened)), 40) for key in keys}
    print("  ".join(key[:40].ljust(widths[key]) for key in keys))
    for flat in flattened:
        cells = []
        for key in keys:
            value = str(flat.get(key, ""))
            if len(value) > widths[key]:
                value = value[: widths[key] - 1] + "…"
            cells.append(value.ljust(widths[key]))
        print("  ".join(cells))
    print()
    print(f"{len(flattened)} row(s).")


def flatten(value, prefix, out):
    if isinstance(value, dict):
        for key, item in value.items():
            flatten(item, f"{prefix}.{key}" if prefix else key, out)
    elif isinstance(value, list):
        out[prefix] = ", ".join(str(v) for v in value)
    else:
        out[prefix] = value


# ---------------------------------------------------------------- args

def parse(args, valued=(), flags=()):
    pos, opts = [], {}
    i = 0
    while i < len(args):
        item = args[i]
        if item.startswith("--"):
            key = item[2:]
            if key in valued:
                if i + 1 >= len(args):
                    fail(f"--{key} needs a value")
                opts[key] = args[i + 1]
                i += 2
            elif key in flags:
                opts[key] = True
                i += 1
            else:
                fail(f"unknown option --{key}")
        else:
            pos.append(item)
            i += 1
    return pos, opts


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return
    if not args:
        cmd_status()
        return
    command, rest = args[0], args[1:]
    if command == "setup":
        pos, opts = parse(rest, valued=("client-id", "api-version"), flags=("quiet",))
        cmd_setup(pos, opts)
    elif command == "login":
        pos, opts = parse(rest, valued=("code",))
        cmd_login(pos, opts)
    elif command == "accounts":
        cmd_accounts()
    elif command == "customer":
        pos, opts = parse(rest, valued=("id",))
        cmd_customer(pos, opts)
    elif command == "manager":
        pos, opts = parse(rest, valued=("id",))
        cmd_manager(pos, opts)
    elif command == "version":
        pos, opts = parse(rest)
        cmd_version(pos, opts)
    elif command == "campaigns":
        pos, opts = parse(rest, valued=("days",))
        cmd_campaigns(pos, opts)
    elif command == "costs":
        pos, opts = parse(rest, valued=("days", "by"))
        cmd_costs(pos, opts)
    elif command == "report":
        pos, opts = parse(rest, valued=("query",))
        cmd_report(pos, opts)
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nads: stopped")
        sys.exit(1)
