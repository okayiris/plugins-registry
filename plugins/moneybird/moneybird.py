#!/usr/bin/env python3
"""Moneybird accounting, read-only, for Iris.

The API token never enters this script. Every request goes through the vault, which adds the
Bearer token itself; we only see the answer. Moneybird API v2, base https://moneybird.com/api/v2.

  moneybird                              are we connected, and to which administrations?
  moneybird administraties               all administrations
  moneybird administratie <id>           one administration in more detail
  moneybird contacten [zoek]             contacts, newest first, optionally filtered
  moneybird facturen [aantal]            the last sales invoices (default 10)
  moneybird openstaand                   unpaid invoices with the total outstanding
  moneybird oauth start                  the Moneybird authorization link
  moneybird oauth koppel <code>          exchange an authorization code (through the vault)
  moneybird oauth status                 is the token in the vault usable?

Reads only. This command never sends, changes or deletes anything, and never shows a secret.

Owner setup (once):
  kluis vraag moneybird-oauth --domein moneybird.com "Moneybird OAuth client secret"
  kluis vraag moneybird --domein moneybird.com "Moneybird API access token"
The client id is public; save it once with `moneybird oauth start <client-id>`.
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.parse

API = "https://moneybird.com/api/v2"
AUTHORIZE = "https://moneybird.com/oauth/authorize"
TOKEN = "https://moneybird.com/oauth/token"
REDIRECT = "urn:ietf:wg:oauth:2.0:oob"
SCOPE = "sales_invoices documents settings"
HERE = os.path.dirname(os.path.realpath(__file__))
SETTINGS = os.path.join(HERE, "settings.json")
ITEM = "moneybird"
ITEM_OAUTH = "moneybird-oauth"


# --- helpers ---------------------------------------------------------------------------------

def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def kluis():
    for name in ("kluis", "vault"):
        found = shutil.which(name)
        if found:
            return found
    for path in (os.path.expanduser("~/.local/bin/kluis"), "/usr/local/bin/vault"):
        if os.path.exists(path):
            return path
    return None


def vault_call(item, method, url, body=None, header=None):
    """Let the vault make the call. Returns (status, text, error). The token stays in the vault."""
    exe = kluis()
    if not exe:
        return None, "", "the vault command is not on this system"
    cmd = [exe, "doe", item, method, url]
    if body:
        cmd.append(body)
    if header:
        cmd += ["--kop", header]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None, "", "Moneybird did not answer in time"
    if r.returncode != 0:
        return None, "", (r.stderr or r.stdout).strip() or "the vault refused"
    out = r.stdout.splitlines()
    status = None
    if out and out[0].startswith("status "):
        try:
            status = int(out[0].split()[1])
        except (IndexError, ValueError):
            status = None
        out = out[1:]
    return status, "\n".join(out), None


def api(path, params=None):
    """GET an API path (relative to the base). Returns (json, error)."""
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    status, text, err = vault_call(ITEM, "GET", url, header="Authorization: Bearer {g}")
    if err:
        return None, err
    if status == 401:
        return None, "the Moneybird token was refused (401). Put a fresh one in the vault."
    if status != 200:
        return None, f"Moneybird answered {status}: {text[:200]}"
    try:
        return json.loads(text), None
    except ValueError:
        return None, "Moneybird did not return JSON"


def money(value, currency="EUR"):
    try:
        n = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return str(value)
    s = f"{n:,.2f}".replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")
    return ("\u20ac " + s) if currency == "EUR" else f"{s} {currency}"


def contact_name(inv):
    c = inv.get("contact") or {}
    return c.get("company_name") or " ".join(x for x in (c.get("firstname"), c.get("lastname")) if x) or "(no name)"


def pick_administration(args):
    """The administration to work on: --administratie, settings, or the only one available."""
    admins, err = api("/administrations.json")
    if err:
        sys.exit(f"moneybird: {err}")
    if not admins:
        sys.exit("moneybird: no administration found for this token.")
    wanted = None
    if "--administratie" in args:
        i = args.index("--administratie")
        if i + 1 < len(args):
            wanted = str(args[i + 1])
            args = args[:i] + args[i + 2:]
    if not wanted:
        wanted = str(load_settings().get("administration_id") or "")
    if wanted:
        for a in admins:
            if str(a.get("id")) == wanted:
                return a, admins, args
        print(f"moneybird: administration {wanted} not found; using the first one.")
    return admins[0], admins, args


def help_text():
    print(__doc__.strip())


# --- commands --------------------------------------------------------------------------------

def cmd_status():
    status, text, err = vault_call(ITEM, "GET", API + "/administrations.json",
                                   header="Authorization: Bearer {g}")
    if err:
        print("Moneybird is not connected yet.")
        print(f"({err})")
        print("Put the keys in the vault, then try again:")
        print("  kluis vraag moneybird-oauth --domein moneybird.com \"Moneybird OAuth client secret\"")
        print("  kluis vraag moneybird --domein moneybird.com \"Moneybird API access token\"")
        print("Client id (public) and the OAuth link: `moneybird oauth start <client-id>`.")
        return
    if status == 401:
        print("The Moneybird token in the vault was refused (401). Put a fresh token in the vault.")
        return
    if status != 200:
        print(f"Moneybird answered {status}: {text[:200]}")
        return
    try:
        admins = json.loads(text)
    except ValueError:
        admins = []
    ids = [str(a.get("id")) for a in admins]
    chosen = load_settings().get("administration_id")
    if chosen and str(chosen) in ids:
        active = chosen
    else:
        active = ids[0] if ids else None
    print(f"Moneybird is connected, with {len(admins)} administration(s).")
    print("Active: " + (active or "none"))
    for a in admins:
        print(f"  {a.get('id')}  {a.get('name')}  {a.get('currency', '')}")


def cmd_administrations():
    admins, err = api("/administrations.json")
    if err:
        sys.exit(f"moneybird: {err}")
    chosen = str(load_settings().get("administration_id") or "")
    for a in admins:
        mark = " *" if str(a.get("id")) == chosen else ""
        print(f"{a.get('id')}  {a.get('name')}  {a.get('currency', '')}{mark}")
    if not admins:
        print("no administrations")
    elif chosen:
        print("* = the one this command uses by default")


def cmd_administratie(args):
    adm, admins, _ = pick_administration(args)
    save_settings(load_settings() | {"administration_id": str(adm.get("id"))})
    print(f"{adm.get('name')}")
    print(f"  id: {adm.get('id')}")
    print(f"  currency: {adm.get('currency')}   country: {adm.get('country')}   language: {adm.get('language')}")
    print(f"  time zone: {adm.get('time_zone')}   access: {adm.get('access')}")
    if adm.get("period_start_date"):
        print(f"  period starts: {adm.get('period_start_date')}")
    if adm.get("period_locked_until"):
        print(f"  locked until: {adm.get('period_locked_until')}")
    if adm.get("suspended"):
        print("  suspended: yes")


def cmd_contacten(args):
    adm, _, rest = pick_administration(args)
    query = " ".join(a for a in rest if not a.startswith("--")) or None
    params = {"per_page": 50}
    if query:
        params["query"] = query
    contacts, err = api(f"/{adm['id']}/contacts.json", params)
    if err:
        sys.exit(f"moneybird: {err}")
    if not contacts:
        print("no contacts found" + (f" for \u201c{query}\u201d" if query else ""))
        return
    for c in contacts[:25]:
        name = c.get("company_name") or " ".join(x for x in (c.get("firstname"), c.get("lastname")) if x) or "(no name)"
        bits = [x for x in (c.get("email"), c.get("city")) if x]
        print(f"{name}" + (f"  ({', '.join(bits)})" if bits else ""))
    if len(contacts) > 25:
        print(f"... and {len(contacts) - 25} more")


def cmd_facturen(args):
    adm, _, rest = pick_administration(args)
    n = 10
    for a in rest:
        if a.isdigit():
            n = max(1, min(100, int(a)))
    invoices, err = api(f"/{adm['id']}/sales_invoices.json", {"per_page": n})
    if err:
        sys.exit(f"moneybird: {err}")
    if not invoices:
        print("no invoices found in the current financial year.")
        return
    for inv in invoices:
        total = inv.get("total_price_incl_tax")
        if inv.get("state") in ("open", "late", "reminded", "pending_payment") and inv.get("total_unpaid"):
            total = inv.get("total_unpaid")
        num = str(inv.get("invoice_id") or "")
        state = str(inv.get("state") or "")
        print(f"{num:>10}  {state:<16} {money(total, inv.get('currency')):>12}  "
              f"{inv.get('invoice_date') or ''}  {contact_name(inv)}")
    print(f"{len(invoices)} invoices (unpaid ones show what is still open).")


def cmd_openstaand(args):
    adm, _, _ = pick_administration(args)
    states = ["open", "late", "reminded", "pending_payment"]
    invoices, err = api(f"/{adm['id']}/sales_invoices.json",
                        {"per_page": 100, "filter": "state:" + "|".join(states)})
    if err:
        # Older API versions do not know the combined state filter; fall back to all and filter here.
        invoices, err2 = api(f"/{adm['id']}/sales_invoices.json", {"per_page": 100})
        if err2:
            sys.exit(f"moneybird: {err}")
        invoices = [inv for inv in invoices if inv.get("state") in states]
    currency = adm.get("currency", "EUR")
    total = 0.0
    for inv in invoices:
        try:
            total += float(str(inv.get("total_unpaid") or 0).replace(",", "."))
        except ValueError:
            pass
    if not invoices:
        print("nothing outstanding.")
        return
    for inv in invoices:
        num = str(inv.get("invoice_id") or "")
        print(f"{num:>10}  {inv.get('due_date') or '':<12} "
              f"{money(inv.get('total_unpaid'), inv.get('currency') or currency):>12}  {contact_name(inv)}")
    print(f"{len(invoices)} open invoices, together {money(total, currency)} outstanding.")


def cmd_oauth(args):
    rest = args[1:]
    if not rest or rest[0] == "help":
        print("moneybird oauth start [client-id]      the authorization link\n"
              "moneybird oauth koppel <code|url>      exchange the code for tokens (via the vault)\n"
              "moneybird oauth status                 is the token usable?")
        return
    if rest[0] == "status":
        cmd_status()
        return
    if rest[0] == "start":
        client_id = rest[1] if len(rest) > 1 else load_settings().get("client_id")
        if client_id:
            save_settings(load_settings() | {"client_id": client_id})
        if not client_id:
            print("No client id known yet. Register an app at https://moneybird.com/user/applications/new,")
            print("then save the (public) client id once with:  moneybird oauth start <client-id>")
            print(f"Private part into the vault:  kluis vraag {ITEM_OAUTH} --domein moneybird.com "
                  '"Moneybird OAuth client secret"')
            return
        params = {"client_id": client_id, "redirect_uri": REDIRECT,
                  "response_type": "code", "scope": SCOPE}
        url = AUTHORIZE + "?" + urllib.parse.urlencode(params)
        print("Open this link, log in as the administration owner and authorize:")
        print(url)
        print("\nMoneybird shows a code in the browser. Hand it over with:")
        print("  moneybird oauth koppel <code>")
        return
    if rest[0] == "koppel":
        if len(rest) < 2:
            sys.exit("moneybird oauth koppel needs the code or the full redirect URL")
        raw = " ".join(rest[1:]).strip()
        code = raw
        if "code=" in raw:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [raw])[0]
        client_id = load_settings().get("client_id")
        if not client_id:
            sys.exit("moneybird: no client id yet; run `moneybird oauth start <client-id>` first.")
        body = (f"client_id={urllib.parse.quote(client_id)}&client_secret={{g}}"
                f"&code={urllib.parse.quote(code)}&redirect_uri={urllib.parse.quote(REDIRECT)}"
                f"&grant_type=authorization_code")
        status, text, err = vault_call(ITEM_OAUTH, "POST", TOKEN, body=body)
        if err:
            sys.exit(f"moneybird: {err}")
        if status != 200:
            sys.exit(f"moneybird: Moneybird refused the exchange ({status}): {text[:200]}")
        try:
            done = json.loads(text)
        except ValueError:
            done = {}
        scope = done.get("scope", "")
        # The vault did the exchange; the token itself stays out of our logs on purpose.
        print("The code was exchanged for a token (the token is not shown, it is a secret).")
        print(f"Scope: {scope or 'as registered'}")
        print("Put the access token in the vault so this command can use it:")
        print(f"  kluis vraag {ITEM} --domein moneybird.com \"Moneybird API access token\"")
        print("If Moneybird gave a refresh token too, keep it as the \u201crefresh\u201d field on that item.")
        return
    sys.exit(__doc__)


def main():
    args = sys.argv[1:]
    if not args:
        cmd_status()
    elif args[0] in ("-h", "--help", "help"):
        help_text()
    elif args[0] == "administraties":
        cmd_administrations()
    elif args[0] == "administratie":
        cmd_administratie(args)
    elif args[0] == "contacten":
        cmd_contacten(args)
    elif args[0] == "facturen":
        cmd_facturen(args)
    elif args[0] == "openstaand":
        cmd_openstaand(args)
    elif args[0] == "oauth":
        cmd_oauth(args)
    else:
        print(f"moneybird: unknown command \u201c{args[0]}\u201d\n")
        help_text()


if __name__ == "__main__":
    main()
