#!/usr/bin/env python3
"""Stripe, read-only, for Iris.

See your own Stripe balance, payments, customers, invoices, subscriptions and monthly
revenue with your own restricted key. Version 1.0.0 only reads: every request is a GET to
api.stripe.com, and nothing is ever created, changed or refunded.

  stripe balance                          the available and pending balance per currency
  stripe payments [--limit <n>]           the latest payments (default 10, at most 100)
  stripe customers [--search <term>] [--limit <n>]
                                          the latest customers, or a search on name and email
  stripe invoices [--status <status>] [--limit <n>]
                                          the latest invoices, optionally by status
  stripe subscriptions [--status <status>] [--limit <n>]
                                          the latest subscriptions, optionally by status
  stripe revenue [--month <YYYY-MM>]      gross, refunded and net revenue of a month (UTC)
  stripe key                              is a key in the vault, and is it accepted
  stripe key ask                          let the owner paste a read-only key in the vault
  stripe key item <name> [--domain <d>]   use another vault item and domain

The key never enters this script. Every call goes through the vault, which adds the
Authorization header itself; only the answer comes back. Ask for a restricted key with
read-only permissions once:

  kluis vraag stripe-api --domein stripe.com "Stripe restricted API key (read-only)"

A restricted key starts with rk_live_ or rk_test_. Never use a full secret key (sk_) here.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG = os.path.join(HERE, "config.json")
API = "https://api.stripe.com"
DEFAULT_ITEM = "stripe-api"
DEFAULT_DOMAIN = "stripe.com"
MAX_LIMIT = 100
PAGE_CAP = 2000

# Stripe amounts are in the smallest currency unit. Most currencies have two decimals,
# these have none, and a few have three.
ZERO_DECIMAL = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg", "rwf", "ugx",
    "vnd", "vuv", "xaf", "xof", "xpf",
}
THREE_DECIMAL = {"bhd", "jod", "kwd", "omr", "tnd"}

INVOICE_STATUSES = ("draft", "open", "paid", "uncollectible", "void")
SUB_STATUSES = ("active", "past_due", "unpaid", "canceled", "incomplete",
                "incomplete_expired", "trialing", "all")


def fail(text):
    print("stripe: " + text)
    sys.exit(1)


# ---------------------------------------------------------------- config

def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(data):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, CONFIG)


def item():
    return str(load_config().get("item") or DEFAULT_ITEM).strip()


def domain():
    return str(load_config().get("domain") or DEFAULT_DOMAIN).strip()


# ---------------------------------------------------------------- the vault

def vault_bin():
    for name in ("kluis", "vault"):
        found = shutil.which(name)
        if found:
            return found
    for path in (os.path.expanduser("~/.local/bin/kluis"), "/usr/local/bin/vault"):
        if os.path.isfile(path):
            return path
    return None


def vault_call(url, header=None, timeout=90):
    """Let the vault make the GET call. Returns (status, body, error); the key stays in the vault."""
    if not (url == API or url.startswith(API + "/")):
        return None, "", "refused: only api.stripe.com is allowed"
    exe = vault_bin()
    if not exe:
        return None, "", "the vault command is not on this system"
    cmd = [exe, "doe", item(), "GET", url]
    if header:
        cmd += ["--kop", header]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "", "Stripe did not answer in time"
    except OSError as e:
        return None, "", f"the vault could not be started ({e})"
    lines = (r.stdout or "").splitlines()
    status = None
    if lines and lines[0].startswith("status "):
        try:
            status = int(lines[0].split()[1])
        except (IndexError, ValueError):
            status = None
        lines = lines[1:]
    body = "\n".join(lines).strip()
    if status is None:
        err = (r.stderr or "").strip() or (r.stdout or "").strip()
        return None, "", err or "no answer from the vault"
    return status, body, None


def stripe_error(status, body):
    """A clear message for Stripe's own error, without ever echoing the key."""
    message = ""
    try:
        parsed = json.loads(body)
        err = parsed.get("error") or {}
        message = str(err.get("message") or "")
    except (ValueError, AttributeError):
        message = (body or "")[:300]
    if status == 401:
        return ("Stripe refused the key (401). The key may be wrong or revoked, or it is for "
                "another mode. Check the vault item.")
    if status == 403:
        extra = f" Stripe says: {message}" if message else ""
        return ("Stripe refused this request (403): the restricted key has no read permission "
                "for this resource." + extra)
    if status == 404:
        return f"Stripe could not find that resource (404).{(' ' + message) if message else ''}"
    if status == 429:
        return "Stripe rate limit reached (429). Try again in a moment."
    if status and status >= 500:
        return f"Stripe had a server error ({status}). Try again later."
    return f"Stripe answered {status}: {message or (body or '')[:200]}"


def api(path, params=None):
    """GET an API path (relative to the base). Returns (json, error)."""
    url = API + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    status, body, err = vault_call(url, header="Authorization: Bearer {g}")
    if err:
        low = err.lower()
        if "item bestaat niet" in low or "unknown item" in low or "kluis" in low or "vault" in low:
            return None, ("no Stripe key in the vault yet. Ask for a restricted read-only key "
                          "once with `stripe key ask`.")
        return None, err
    if status != 200:
        return None, stripe_error(status, body)
    try:
        return json.loads(body), None
    except ValueError:
        return None, "Stripe did not return JSON"


def list_all(path, params, cap=PAGE_CAP):
    """Walk a list endpoint with starting_after. Returns (items, error)."""
    out = []
    starting = None
    while True:
        page = dict(params)
        page["limit"] = 100
        if starting:
            page["starting_after"] = starting
        data, err = api(path, page)
        if err:
            return out, err
        items = data.get("data") or []
        out.extend(items)
        if not data.get("has_more") or not items or len(out) >= cap:
            break
        starting = items[-1].get("id")
    return out, None


# ---------------------------------------------------------------- formatting

def money(amount, currency):
    try:
        n = int(amount)
    except (TypeError, ValueError):
        return f"{amount} {str(currency).upper()}"
    cur = str(currency or "").lower()
    if cur in ZERO_DECIMAL:
        decimals = 0
    elif cur in THREE_DECIMAL:
        decimals = 3
    else:
        decimals = 2
    value = n / (10 ** decimals)
    return f"{cur.upper()} {value:,.{decimals}f}"


def when(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return "?"


def clip(text, width=42):
    text = str(text or "").replace("\n", " ").strip() or "-"
    return text if len(text) <= width else text[: width - 3] + "..."


# ---------------------------------------------------------------- arguments

def split_args(args):
    free, opts = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                opts[a[2:]] = args[i + 1]
                i += 2
            else:
                opts[a[2:]] = True
                i += 1
        else:
            free.append(a)
            i += 1
    return free, opts


def limit_of(opts, default=10):
    if "limit" not in opts:
        return default
    if opts["limit"] is True:
        fail(f"--limit needs a number between 1 and {MAX_LIMIT}")
    try:
        n = int(opts["limit"])
    except (TypeError, ValueError):
        fail(f"--limit must be a number between 1 and {MAX_LIMIT}")
    if not 1 <= n <= MAX_LIMIT:
        fail(f"--limit must be between 1 and {MAX_LIMIT}")
    return n


def status_of(opts, allowed, what):
    if "status" not in opts:
        return None
    if opts["status"] is True:
        fail(f"--status for {what} must be one of: " + ", ".join(allowed))
    value = str(opts["status"]).lower()
    if value not in allowed:
        fail(f"--status for {what} must be one of: " + ", ".join(allowed))
    return value


# ---------------------------------------------------------------- commands

def cmd_balance(args):
    data, err = api("/v1/balance")
    if err:
        fail(err)
    mode = "live" if data.get("livemode") else "test"
    print(f"Stripe balance ({mode} mode)")
    shown = False
    for label, key in (("Available", "available"), ("Pending", "pending")):
        rows = data.get(key) or []
        if rows:
            print(f"{label}:")
            for row in rows:
                print(f"  {money(row.get('amount'), row.get('currency'))}")
            shown = True
    if not shown:
        print("  no funds on the balance")


def cmd_payments(args):
    _free, opts = split_args(args)
    data, err = api("/v1/charges", {"limit": limit_of(opts)})
    if err:
        fail(err)
    charges = data.get("data") or []
    if not charges:
        print("No payments found.")
        return
    print(f"Last {len(charges)} payment(s):")
    for c in charges:
        amount = money(c.get("amount"), c.get("currency"))
        status = str(c.get("status") or "?")
        paid = "paid" if c.get("paid") else "unpaid"
        billing = c.get("billing_details") or {}
        who = (c.get("description") or billing.get("name") or c.get("receipt_email")
               or c.get("customer") or "-")
        print(f"{when(c.get('created'))}  {amount:>16}  {status:<9} {paid:<6}  {clip(who)}")


def cmd_customers(args):
    _free, opts = split_args(args)
    limit = limit_of(opts)
    search = opts.get("search")
    if search is True:
        fail("--search needs a term")
    if search:
        term = str(search).strip()
        if not term:
            fail("--search needs a term")
        query = f"name~{json.dumps(term)} OR email~{json.dumps(term)}"
        data, err = api("/v1/customers/search", {"query": query, "limit": limit})
    else:
        data, err = api("/v1/customers", {"limit": limit})
    if err:
        fail(err)
    customers = data.get("data") or []
    if not customers:
        print("No customers found." if not search else f"No customers found for \"{search}\".")
        return
    print(f"{len(customers)} customer(s):")
    for c in customers:
        print(f"{when(c.get('created'))}  {clip(c.get('name') or '-', 28):<28}  "
              f"{clip(c.get('email') or '-', 30):<30}  {c.get('id')}")


def cmd_invoices(args):
    _free, opts = split_args(args)
    status = status_of(opts, INVOICE_STATUSES, "invoices")
    params = {"limit": limit_of(opts)}
    if status:
        params["status"] = status
    data, err = api("/v1/invoices", params)
    if err:
        fail(err)
    invoices = data.get("data") or []
    if not invoices:
        print("No invoices found.")
        return
    print(f"{len(invoices)} invoice(s):")
    for inv in invoices:
        number = inv.get("number") or inv.get("id") or "-"
        who = inv.get("customer_name") or inv.get("customer_email") or inv.get("customer") or "-"
        print(f"{when(inv.get('created'))}  {clip(number, 16):<16}  {str(inv.get('status') or '?'):<13}  "
              f"total {money(inv.get('total'), inv.get('currency')):>16}  "
              f"due {money(inv.get('amount_due'), inv.get('currency')):>16}  {clip(who, 28)}")


def cmd_subscriptions(args):
    _free, opts = split_args(args)
    status = status_of(opts, SUB_STATUSES, "subscriptions")
    params = {"limit": limit_of(opts)}
    if status:
        params["status"] = status
    data, err = api("/v1/subscriptions", params)
    if err:
        fail(err)
    subs = data.get("data") or []
    if not subs:
        print("No subscriptions found.")
        return
    print(f"{len(subs)} subscription(s):")
    for s in subs:
        first = ((s.get("items") or {}).get("data") or [{}])[0]
        price = first.get("price") or {}
        recurring = price.get("recurring") or {}
        amount = money(price.get("unit_amount"), price.get("currency"))
        interval = recurring.get("interval") or ""
        plan = f"{price.get('nickname') or price.get('id') or '-'} {amount}"
        if interval:
            plan += f"/{interval}"
        nxt = when(s.get("current_period_end")) if s.get("current_period_end") else "-"
        print(f"{when(s.get('created'))}  {str(s.get('status') or '?'):<13}  {clip(plan, 30):<30}  "
              f"next {nxt}  {clip(s.get('customer'), 24)}")


def cmd_revenue(args):
    _free, opts = split_args(args)
    month = opts.get("month")
    now = datetime.now(timezone.utc)
    if month:
        match = re.fullmatch(r"(\d{4})-(\d{2})", str(month))
        if not match:
            fail("--month must be YYYY-MM, for example 2026-09")
        year, mon = int(match.group(1)), int(match.group(2))
        if not 1 <= mon <= 12:
            fail("--month must be a real month, for example 2026-09")
    else:
        year, mon = now.year, now.month
    start = int(datetime(year, mon, 1, tzinfo=timezone.utc).timestamp())
    nxt = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if mon == 12 else datetime(year, mon + 1, 1, tzinfo=timezone.utc)
    end = int(nxt.timestamp())
    charges, err = list_all("/v1/charges", {"created[gte]": start, "created[lt]": end})
    if err:
        fail(err)
    buckets = {}
    for c in charges:
        if c.get("status") != "succeeded" or not c.get("paid"):
            continue
        cur = str(c.get("currency") or "?").lower()
        b = buckets.setdefault(cur, {"gross": 0, "refunded": 0, "count": 0})
        b["gross"] += int(c.get("amount") or 0)
        b["refunded"] += int(c.get("amount_refunded") or 0)
        b["count"] += 1
    print(f"Revenue {year:04d}-{mon:02d} (UTC)")
    if not buckets:
        print("  no successful payments in this month")
    for cur in sorted(buckets):
        b = buckets[cur]
        net = b["gross"] - b["refunded"]
        print(f"  {cur.upper()}  gross {money(b['gross'], cur)}  "
              f"refunded {money(b['refunded'], cur)}  net {money(net, cur)}  "
              f"({b['count']} payments)")
    if len(charges) >= PAGE_CAP:
        print(f"  note: stopped after {PAGE_CAP} payments, the totals may be incomplete")


def cmd_key(args):
    free, opts = split_args(args)
    sub = free[0] if free else ""
    if sub == "ask":
        exe = vault_bin()
        if not exe:
            fail("the vault command is not on this system")
        cmd = [exe, "vraag", item(), "--domein", domain(),
               "Stripe restricted API key (read-only)"]
        sys.exit(subprocess.run(cmd).returncode)
    if sub == "item":
        if len(free) < 2:
            fail("stripe key item <name> [--domain <domain>]")
        cfg = load_config()
        cfg["item"] = free[1]
        if opts.get("domain") is True:
            fail("--domain needs a value")
        if opts.get("domain"):
            cfg["domain"] = str(opts["domain"])
        save_config(cfg)
        print(f"Vault item set to \"{cfg['item']}\" for domain {cfg['domain']}.")
        return
    if sub:
        fail(f"unknown key subcommand \"{sub}\" (use: ask, item)")
    data, err = api("/v1/balance")
    if err:
        print("Stripe is not connected yet.")
        print(f"  {err}")
        return
    mode = "live" if data.get("livemode") else "test"
    print(f"Stripe is connected, in {mode} mode "
          f"(vault item \"{item()}\", domain {domain()}).")


COMMANDS = {
    "balance": cmd_balance,
    "payments": cmd_payments,
    "customers": cmd_customers,
    "invoices": cmd_invoices,
    "subscriptions": cmd_subscriptions,
    "revenue": cmd_revenue,
    "key": cmd_key,
}


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("help", "--help", "-h"):
        print(__doc__.strip())
        return
    command = args[0]
    handler = COMMANDS.get(command)
    if not handler:
        fail(f"unknown command \"{command}\". Use: " + ", ".join(COMMANDS))
    handler(args[1:])


if __name__ == "__main__":
    main()
