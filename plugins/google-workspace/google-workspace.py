#!/usr/bin/env python3
"""Google Workspace for Iris: Gmail, Calendar, Contacts and Tasks, with your own Google app.

  gmail                                       what is set up, and what still needs a link
  gmail setup <client-id>                     store your OAuth client id and ask the vault for its secret
  gmail connect                               print the consent URL (OAuth 2.0 with PKCE)
  gmail connect --code <code|url>             finish the login with the code from the redirect
  gmail connect --again                       forget the tokens and start a fresh login
  gmail who                                   the connected Google account

  gmail mail list [n] [--q "<gmail query>"]   the latest mail, e.g. --q "is:unread newer_than:2d"
  gmail mail read <id>                        one message
  gmail mail draft <to> "<subject>" "<body>"  a draft in your Gmail, not sent
  gmail mail send <to> "<subject>" "<body>"   make a draft; nothing is sent yet
  gmail mail send --ja <draft-id>             send that exact draft, only after your yes

  gmail cal list [days] [--max n]             what is coming up on the primary calendar
  gmail cal add "<title>" <start> [end] [--where ..] [--note ..] [--with a@b,c@d]
  gmail cal add --ja <id>                     create an event with guests, only after your yes

  gmail contacts list [--max n]               your contacts
  gmail contacts search "<text>"              search your contacts

  gmail tasks list [--list <id>]              your task lists and open tasks
  gmail tasks add "<title>" [--list <id>] [--due 2026-10-01] [--note ..]
  gmail tasks done <task-id> [--list <id>]    mark a task completed

Reading is free. Sending mail and inviting guests never happen from one command: that command makes a
draft, shows it, and only a second command with the exact draft id sends or creates it. The app's client
secret stays in the vault (kluis); this tool never sees it and never prints a token.
"""

import base64
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

HERE = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(HERE, ".state.json")
TOKENS = os.path.join(HERE, ".token.json")

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1"
CALENDAR = "https://www.googleapis.com/calendar/v3"
PEOPLE = "https://people.googleapis.com/v1"
TASKS = "https://tasks.googleapis.com/tasks/v1"

# Google allows any loopback port for a Desktop app; the owner only copies the code back, this tool
# never listens here. Register this exact URL in the OAuth client.
REDIRECT = "http://localhost:8765/callback"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/tasks",
]

VAULT_ITEM = "google-workspace"
VAULT_DOMAIN = "oauth2.googleapis.com"
DRAFT_TTL = 3600  # a draft must be approved within an hour


def out(text=""):
    print(text)


def fail(text):
    print(f"gmail: {text}")
    sys.exit(1)


# ---------------------------------------------------------------- state

def load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else fallback
    except (OSError, ValueError):
        return fallback


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_state():
    return load_json(STATE, {})


def save_state(s):
    save_json(STATE, s)


def load_tokens():
    return load_json(TOKENS, {})


def save_tokens(t):
    save_json(TOKENS, t)


# ---------------------------------------------------------------- vault

def vault_bin():
    p = shutil.which("kluis") or shutil.which("vault")
    if p:
        return p
    for cand in (os.path.expanduser("~/.local/bin/kluis"), "/usr/local/bin/vault"):
        if os.path.isfile(cand):
            return cand
    return None


def norm_domain(value):
    value = (value or "").strip().lower()
    value = urllib.parse.urlparse(value if "://" in value else "//" + value).hostname or value
    return value.split(":")[0].rstrip("/")


def vault_items():
    exe = vault_bin()
    if not exe:
        return []
    try:
        proc = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    items = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        parts = [p for p in line.split("  ") if p.strip()]
        if len(parts) >= 3:
            items.append({"name": parts[0].strip(), "user": parts[1].strip(), "domain": parts[2].strip()})
    return items


def secret_item():
    for item in vault_items():
        if norm_domain(item["domain"]) == VAULT_DOMAIN:
            return item
    return None


def client_id():
    item = secret_item()
    user = (item or {}).get("user", "")
    return "" if user in ("", "-") else user


def vault_call(item, method, url, body=None, header=None, timeout=90):
    """Let the vault make the call; {g} in the body is the secret. Returns (status, text)."""
    exe = vault_bin()
    if not exe:
        return None, "the vault command (kluis) is not on this system"
    cmd = [exe, "doe", item, method, url]
    if body is not None:
        cmd.append(body)
    if header:
        cmd += ["--kop", header]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "the vault did not answer in time"
    except OSError as exc:
        return None, str(exc)
    if not proc.stdout.strip():
        return None, (proc.stderr.strip() or "the vault gave no answer")
    first, _, rest = proc.stdout.partition("\n")
    status = None
    if first.startswith("status "):
        try:
            status = int(first.split()[1])
        except (IndexError, ValueError):
            pass
    return status, rest.strip()


def vault_ask():
    """Ask the owner to paste the OAuth client secret into the vault window."""
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system")
    args = [exe, "vraag", VAULT_ITEM, "--domein", VAULT_DOMAIN,
            "Google OAuth client secret"]
    cid = client_id()
    if cid:
        args += ["--gebruiker", cid]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=200)
    except OSError as exc:
        fail(f"the vault did not answer ({exc})")
    if proc.returncode != 0:
        fail("the client secret is not in the vault: " +
             (proc.stderr or proc.stdout or "cancelled").strip() +
             f'\nRun: kluis vraag {VAULT_ITEM} --domein {VAULT_DOMAIN} --gebruiker <client-id> "Google OAuth client secret"')


def ensure_secret():
    if secret_item():
        return True
    vault_ask()
    return bool(secret_item())


# ---------------------------------------------------------------- http

def http(method, url, data=None, headers=None, timeout=45):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except OSError as e:
        return 0, str(e)


def google_error(body):
    try:
        d = json.loads(body)
    except (ValueError, TypeError):
        return str(body)
    if isinstance(d, dict):
        err = d.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("status") or ""
            errs = err.get("errors") or []
            if errs and isinstance(errs[0], dict) and errs[0].get("message"):
                msg = errs[0]["message"] + (f" - {msg}" if msg and msg != errs[0]["message"] else "")
            return msg or body
        if isinstance(err, str):
            return err + (f": {d.get('error_description')}" if d.get("error_description") else "")
    return body


def parse_body(body):
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def api(method, url, token=None, params=None, json_body=None, raw_body=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif raw_body is not None:
        data = raw_body
    status, body = http(method, url, data=data, headers=headers)
    d = parse_body(body)
    if status >= 400 or (isinstance(d, dict) and "error" in d):
        raise RuntimeError(google_error(body))
    return d if d is not None else body


# ---------------------------------------------------------------- oauth

def parse_param(text, key):
    m = re.search(r"[?&#]" + re.escape(key) + r"=([^&#\s]+)", text or "")
    return urllib.parse.unquote(m.group(1)) if m else None


def pkce():
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def auth_url(cid, state, challenge):
    q = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": REDIRECT,
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{AUTH}?{q}"


def form_body(pairs):
    parts = []
    for key, value in pairs:
        if value == "{g}":
            parts.append(f"{key}={{g}}")
        else:
            parts.append(f"{key}={urllib.parse.quote(str(value), safe='')}")
    return "&".join(parts)


def token_request(pairs):
    """Exchange or refresh a token inside the vault, so the client secret never leaves it."""
    item = secret_item()
    if not item:
        fail(f"no Google client secret in the vault. Run `gmail setup <client-id>` first.")
    status, text = vault_call(item["name"], "POST", TOKEN, body=form_body(pairs),
                              header="Content-Type: application/x-www-form-urlencoded")
    if status is None:
        fail(f"the vault refused the call: {text}")
    d = parse_body(text) or {}
    if status != 200 or not d.get("access_token"):
        fail("Google refused the token: " + google_error(text))
    return d


def start_link(force=False):
    cid = client_id()
    if not cid:
        fail("no client id yet. Run `gmail setup <client-id>` with the id of your Google OAuth client.")
    ensure_secret()
    st = load_state()
    verifier, challenge = pkce()
    st["code_verifier"] = verifier
    st["oauth_state"] = secrets.token_urlsafe(24)
    if force:
        save_tokens({})
    save_state(st)
    out(f"Google OAuth client: {cid} (from the vault).")
    out()
    out("Open this URL, sign in, and approve access:")
    out(auth_url(cid, st["oauth_state"], challenge))
    out()
    out("Google sends you to a localhost page that cannot load here; that is expected. Copy the whole")
    out("address bar and run this to finish:")
    out('  gmail connect --code "<paste the whole URL or just the code>"')
    out(f"Make sure {REDIRECT} is registered as a redirect URI on your OAuth client.")


def finish_link(pasted):
    cid = client_id()
    st = load_state()
    verifier = st.get("code_verifier")
    if not cid or not verifier:
        fail("no login in progress. Run `gmail connect` first.")
    code = parse_param(pasted, "code") or (pasted.strip() if pasted and "=" not in pasted else None)
    if not code:
        err = parse_param(pasted, "error_description") or parse_param(pasted, "error")
        fail("no code in that paste" + (f": {err}" if err else "") +
             '. Copy the whole redirect URL, or just the "code" value.')
    got_state = parse_param(pasted, "state")
    if got_state and st.get("oauth_state") and got_state != st["oauth_state"]:
        fail("the login state does not match. Run `gmail connect` again for a fresh URL.")

    d = token_request([
        ("grant_type", "authorization_code"),
        ("code", code),
        ("client_id", cid),
        ("redirect_uri", REDIRECT),
        ("code_verifier", verifier),
        ("client_secret", "{g}"),
    ])
    tokens = {
        "access_token": d["access_token"],
        "expires_at": int(time.time()) + int(d.get("expires_in") or 3600),
    }
    if d.get("refresh_token"):
        tokens["refresh_token"] = d["refresh_token"]
    save_tokens(tokens)
    st.pop("code_verifier", None)
    st.pop("oauth_state", None)
    save_state(st)
    who()


def ensure_token():
    tokens = load_tokens()
    token = tokens.get("access_token")
    if not token:
        fail("not connected. Run `gmail connect` first.")
    if int(tokens.get("expires_at") or 0) - int(time.time()) > 60:
        return token
    refresh = tokens.get("refresh_token")
    if not refresh:
        fail("the access token expired and there is no refresh token. Run `gmail connect` again.")
    cid = client_id()
    if not cid:
        fail("no client id in the vault. Run `gmail setup <client-id>` first.")
    d = token_request([
        ("grant_type", "refresh_token"),
        ("refresh_token", refresh),
        ("client_id", cid),
        ("client_secret", "{g}"),
    ])
    tokens["access_token"] = d["access_token"]
    tokens["expires_at"] = int(time.time()) + int(d.get("expires_in") or 3600)
    if d.get("refresh_token"):
        tokens["refresh_token"] = d["refresh_token"]
    save_tokens(tokens)
    return tokens["access_token"]


# ---------------------------------------------------------------- pending drafts (approval)

def new_pending(kind, payload):
    st = load_state()
    did = secrets.token_hex(3)
    payload = dict(payload)
    payload["kind"] = kind
    payload["ts"] = int(time.time())
    st.setdefault("pending", {})[did] = payload
    save_state(st)
    return did


def take_pending(did, kind):
    st = load_state()
    d = (st.get("pending") or {}).get(did)
    if not d:
        fail(f"no draft {did}. Make one first.")
    if d.get("kind") != kind:
        fail(f"draft {did} is not a {kind} draft.")
    if int(time.time()) - int(d.get("ts", 0)) > DRAFT_TTL:
        st["pending"].pop(did, None)
        save_state(st)
        fail(f"draft {did} is more than an hour old; make a fresh one.")
    st["pending"].pop(did, None)
    save_state(st)
    return d


# ---------------------------------------------------------------- formatting

def b64d(data):
    if not data:
        return ""
    pad = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def header(msg, name):
    for h in (msg.get("payload") or {}).get("headers") or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value") or ""
    return ""


def message_text(payload):
    """Walk the MIME tree and return the plain text, or a rough text from HTML."""
    if not isinstance(payload, dict):
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body") or {}
    if mime == "text/plain" and body.get("data"):
        return b64d(body["data"])
    for part in payload.get("parts") or []:
        text = message_text(part)
        if text.strip():
            return text
    if mime == "text/html" and body.get("data"):
        html = b64d(body["data"])
        html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
        html = re.sub(r"(?i)<br\s*/?>", "\n", html)
        html = re.sub(r"(?i)</p>", "\n\n", html)
        html = re.sub(r"<[^>]+>", "", html)
        return html.unescape(re.sub(r"\n{3,}", "\n\n", html)).strip()
    return ""


def short(text, n=90):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "..."


# ---------------------------------------------------------------- gmail

def mail_list(pos, flags):
    token = ensure_token()
    n = 10
    if pos:
        try:
            n = int(pos[0])
        except ValueError:
            fail("give a number of messages, e.g. gmail mail list 20")
    n = max(1, min(50, n))
    q = str(flags.get("q") or "")
    d = api("GET", f"{GMAIL}/users/me/messages", token=token,
            params={"maxResults": n, "q": q} if q else {"maxResults": n})
    rows = d.get("messages") or []
    if not rows:
        out("no messages matched")
        return
    for m in rows:
        mid = m.get("id")
        try:
            msg = api("GET", f"{GMAIL}/users/me/messages/{mid}", token=token,
                      params={"format": "metadata", "metadataHeaders": "From,Subject,Date"})
        except RuntimeError as e:
            out(f"{mid}  (could not read: {e})")
            continue
        when = short(header(msg, "Date"), 31)
        out(f"{mid}  {when}  {short(header(msg, 'From'), 28)}")
        out(f"    {short(header(msg, 'Subject') or '(no subject)', 90)}")


def mail_read(pos, flags):
    if not pos:
        fail("use: gmail mail read <id>")
    token = ensure_token()
    msg = api("GET", f"{GMAIL}/users/me/messages/{pos[0]}", token=token, params={"format": "full"})
    out(f"from: {header(msg, 'From')}")
    out(f"to: {header(msg, 'To')}")
    if header(msg, "Cc"):
        out(f"cc: {header(msg, 'Cc')}")
    out(f"date: {header(msg, 'Date')}")
    out(f"subject: {header(msg, 'Subject')}")
    out("<mail>")
    out(message_text(msg.get("payload")).strip() or "(no readable body)")
    out("</mail>")


def build_message(to, subject, body):
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def mail_draft(pos, flags):
    if len(pos) < 3:
        fail('use: gmail mail draft <to> "<subject>" "<body>"')
    token = ensure_token()
    raw = build_message(pos[0], pos[1], " ".join(pos[2:]))
    d = api("POST", f"{GMAIL}/users/me/drafts", token=token, json_body={"message": {"raw": raw}})
    did = (d.get("draft") or {}).get("id") or d.get("id") or "?"
    out(f"draft {did} saved in your Gmail. Nothing has been sent.")


def mail_send(pos, flags):
    if "ja" in flags:
        did = flags.get("ja")
        if not did or did is True:
            fail("use: gmail mail send --ja <draft-id>")
        d = take_pending(str(did), "mail")
        token = ensure_token()
        raw = build_message(d["to"], d["subject"], d["body"])
        r = api("POST", f"{GMAIL}/users/me/messages/send", token=token, json_body={"raw": raw})
        out(f"sent to {d['to']}: {short(d['subject'])} (id {r.get('id', '?')})")
        return
    if len(pos) < 3:
        fail('use: gmail mail send <to> "<subject>" "<body>"')
    if not load_tokens().get("access_token"):
        fail("not connected. Run `gmail connect` first.")
    to, subject, body = pos[0], pos[1], " ".join(pos[2:])
    did = new_pending("mail", {"to": to, "subject": subject, "body": body})
    out(f"DRAFT {did} - nothing has been sent.")
    out()
    out(f"to: {to}")
    out(f"subject: {subject}")
    out()
    out(body)
    out()
    out("Check this on screen, and only after a yes run:")
    out(f"  gmail mail send --ja {did}")


# ---------------------------------------------------------------- calendar

def is_date(value):
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""))


def is_datetime(value):
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", value or ""))


def primary_timezone(token):
    try:
        d = api("GET", f"{CALENDAR}/calendars/primary", token=token)
        return d.get("timeZone") or "UTC"
    except RuntimeError:
        return "UTC"


def add_hours(dt, hours):
    import datetime
    fmt = "%Y-%m-%dT%H:%M:%S" if len(dt) > 16 else "%Y-%m-%dT%H:%M"
    parsed = datetime.datetime.strptime(dt[:19] if len(dt) > 16 else dt, fmt)
    parsed += datetime.timedelta(hours=hours)
    return parsed.strftime(fmt)


def add_days(date, days):
    import datetime
    d = datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def event_body(title, start, end, flags, tz):
    body = {"summary": title}
    if is_date(start):
        stop = end if end and is_date(end) else add_days(start, 1)
        body["start"] = {"date": start}
        body["end"] = {"date": stop}
    elif is_datetime(start):
        stop = end if end and is_datetime(end) else add_hours(start, 1)
        body["start"] = {"dateTime": start, "timeZone": tz}
        body["end"] = {"dateTime": stop, "timeZone": tz}
    else:
        fail("give a start like 2026-10-01T14:00 or 2026-10-01")
    if flags.get("where"):
        body["location"] = str(flags["where"])
    if flags.get("note"):
        body["description"] = str(flags["note"])
    guests = str(flags.get("with") or "").strip()
    if guests:
        body["attendees"] = [{"email": e.strip()} for e in guests.split(",") if e.strip()]
    return body


def cal_list(pos, flags):
    import datetime
    token = ensure_token()
    days = 7
    if pos:
        try:
            days = int(pos[0])
        except ValueError:
            fail("give a number of days, e.g. gmail cal list 14")
    days = max(1, min(365, days))
    now = datetime.datetime.now(datetime.timezone.utc)
    time_min = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    time_max = (now + datetime.timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    maxn = int(flags.get("max") or 25) if str(flags.get("max") or "25").isdigit() else 25
    d = api("GET", f"{CALENDAR}/calendars/primary/events", token=token, params={
        "timeMin": time_min, "timeMax": time_max, "singleEvents": "true",
        "orderBy": "startTime", "maxResults": max(1, min(100, maxn)),
    })
    rows = d.get("items") or []
    if not rows:
        out(f"nothing on the calendar in the next {days} day(s)")
        return
    for e in rows:
        s = e.get("start") or {}
        when = s.get("dateTime") or s.get("date") or ""
        when = when.replace("T", " ")[:16]
        loc = e.get("location") or ""
        out(f"{when}  {short(e.get('summary') or '(no title)', 60)}" + (f"  @ {short(loc, 30)}" if loc else ""))
        out(f"    id {e.get('id')}  {e.get('htmlLink') or ''}".rstrip())


def cal_add(pos, flags):
    if "ja" in flags:
        did = flags.get("ja")
        if not did or did is True:
            fail("use: gmail cal add --ja <draft-id>")
        d = take_pending(str(did), "event")
        token = ensure_token()
        body = d["body"]
        r = api("POST", f"{CALENDAR}/calendars/primary/events", token=token, json_body=body)
        out(f"event created: {body['summary']} (id {r.get('id', '?')})")
        return
    if len(pos) < 2:
        fail('use: gmail cal add "<title>" <start> [end] [--where ..] [--note ..] [--with a@b,c@d]')
    if not load_tokens().get("access_token"):
        fail("not connected. Run `gmail connect` first.")
    token = ensure_token()
    tz = primary_timezone(token)
    title, start = pos[0], pos[1]
    end = pos[2] if len(pos) > 2 else ""
    body = event_body(title, start, end, flags, tz)
    if body.get("attendees"):
        did = new_pending("event", {"body": body})
        out(f"DRAFT {did} - nothing has been created, the guests are not invited yet.")
        out()
        out(f"{body['summary']}  {start}" + (f" - {end}" if end else ""))
        if body.get("location"):
            out(f"where: {body['location']}")
        out("guests: " + ", ".join(g["email"] for g in body["attendees"]))
        out()
        out("Google mails the invitations; check this on screen, and only after a yes run:")
        out(f"  gmail cal add --ja {did}")
        return
    r = api("POST", f"{CALENDAR}/calendars/primary/events", token=token, json_body=body)
    out(f"event created: {body['summary']} (id {r.get('id', '?')})")


# ---------------------------------------------------------------- contacts

def person_name(p):
    names = p.get("names") or []
    return (names[0].get("displayName") if names else "") or ""


def show_person(p):
    name = person_name(p) or "(no name)"
    emails = ", ".join(e.get("value", "") for e in p.get("emailAddresses") or [])
    phones = ", ".join(n.get("value", "") for n in p.get("phoneNumbers") or [])
    out(f"{name}" + (f"  {emails}" if emails else "") + (f"  {phones}" if phones else ""))


def contacts_list(pos, flags):
    token = ensure_token()
    maxn = str(flags.get("max") or "50")
    size = int(maxn) if maxn.isdigit() else 50
    d = api("GET", f"{PEOPLE}/people/me/connections", token=token, params={
        "personFields": "names,emailAddresses,phoneNumbers",
        "pageSize": max(1, min(200, size)),
        "sortOrder": "LAST_MODIFIED_DESCENDING",
    })
    people = d.get("connections") or []
    if not people:
        out("no contacts")
        return
    for p in people:
        show_person(p)


def contacts_search(pos, flags):
    if not pos:
        fail('use: gmail contacts search "<text>"')
    token = ensure_token()
    query = " ".join(pos)
    d = api("GET", f"{PEOPLE}/people:searchContacts", token=token, params={
        "query": query, "readMask": "names,emailAddresses,phoneNumbers",
    })
    results = d.get("results") or []
    if not results:
        out(f"no contacts matched \"{query}\"")
        return
    for r in results:
        show_person(r.get("person") or {})


# ---------------------------------------------------------------- tasks

def task_lists(token):
    d = api("GET", f"{TASKS}/users/@me/lists", token=token, params={"maxResults": 100})
    return d.get("items") or []


def resolve_list(token, flags):
    lid = str(flags.get("list") or "").strip()
    if lid:
        return lid
    lists = task_lists(token)
    if not lists:
        fail("no task list found")
    return lists[0].get("id")


def tasks_list(pos, flags):
    token = ensure_token()
    lists = task_lists(token)
    if not lists:
        out("no task lists")
        return
    wanted = str(flags.get("list") or "")
    for lst in lists:
        if wanted and lst.get("id") != wanted:
            continue
        out(f"{lst.get('title') or '(list)'}  [{lst.get('id')}]")
        try:
            d = api("GET", f"{TASKS}/lists/{lst['id']}/tasks", token=token,
                    params={"maxResults": 100, "showCompleted": "false"})
        except RuntimeError as e:
            out(f"  (could not read: {e})")
            continue
        items = d.get("items") or []
        if not items:
            out("  (no open tasks)")
        for t in items:
            due = (t.get("due") or "")[:10]
            out(f"  {t.get('title')}" + (f"  due {due}" if due else "") + f"  [{t.get('id')}]")
        out()


def tasks_add(pos, flags):
    if not pos:
        fail('use: gmail tasks add "<title>" [--list <id>] [--due 2026-10-01] [--note ..]')
    token = ensure_token()
    body = {"title": " ".join(pos)}
    if flags.get("note"):
        body["notes"] = str(flags["note"])
    if flags.get("due"):
        due = str(flags["due"])
        if not is_date(due):
            fail("give --due as 2026-10-01")
        body["due"] = f"{due}T00:00:00.000Z"
    lid = resolve_list(token, flags)
    r = api("POST", f"{TASKS}/lists/{lid}/tasks", token=token, json_body=body)
    out(f"task added: {r.get('title')} (id {r.get('id', '?')})")


def tasks_done(pos, flags):
    if not pos:
        fail("use: gmail tasks done <task-id> [--list <id>]")
    token = ensure_token()
    lid = resolve_list(token, flags)
    r = api("PATCH", f"{TASKS}/lists/{lid}/tasks/{pos[0]}", token=token,
            json_body={"status": "completed"})
    out(f"task completed: {r.get('title') or pos[0]}")


# ---------------------------------------------------------------- status

def status():
    out("Google Workspace: Gmail, Calendar, Contacts and Tasks, with your own Google app.")
    out()
    cid = client_id()
    if not cid:
        out("Not set up yet. You need:")
        out("  1. a Google Cloud project with the Gmail, Calendar, People and Tasks APIs enabled")
        out("  2. an OAuth client of type \"Desktop app\" with redirect URI " + REDIRECT)
        out("  3. its client id and client secret in the vault")
        out()
        out("Then run: gmail setup <client-id>")
        return
    out(f"OAuth client id: {cid} (from the vault)")
    out(f"Secret: {'in the vault' if secret_item() else 'MISSING (gmail setup <client-id>)'}")
    if not load_tokens().get("access_token"):
        out("Not connected. Run: gmail connect")
        return
    try:
        token = ensure_token()
        profile = api("GET", f"{GMAIL}/users/me/profile", token=token)
        out(f"Connected as {profile.get('emailAddress') or '?'}")
    except RuntimeError as e:
        out(f"Connected, but reading the profile failed: {e}")
    out()
    out("Commands: gmail mail list, gmail mail read, gmail mail draft, gmail mail send,")
    out("          gmail cal list, gmail cal add, gmail contacts list/search,")
    out("          gmail tasks list/add/done")


def who():
    token = ensure_token()
    try:
        profile = api("GET", f"{GMAIL}/users/me/profile", token=token)
        out(f"connected as {profile.get('emailAddress') or '?'}")
    except RuntimeError as e:
        out(f"connected, but reading the profile failed: {e}")


def setup(rest, flags):
    pos, _ = split_args(rest)
    cid = (pos[0] if pos else "") or str(flags.get("client-id") or "")
    if not cid:
        fail("use: gmail setup <client-id>")
    vault_ask_with_user(cid)
    out(f"Saved your Google OAuth client id and secret under \"{VAULT_ITEM}\" in the vault.")
    out("Now run: gmail connect")


def vault_ask_with_user(cid):
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system")
    args = [exe, "vraag", VAULT_ITEM, "--domein", VAULT_DOMAIN, "--gebruiker", cid,
            "Google OAuth client secret"]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=200)
    except OSError as exc:
        fail(f"the vault did not answer ({exc})")
    if proc.returncode != 0:
        fail("the client secret was not saved: " +
             (proc.stderr or proc.stdout or "cancelled").strip())


# ---------------------------------------------------------------- main

def main():
    a = sys.argv[1:]
    if not a:
        status()
        return
    if a[0] in ("help", "--help", "-h"):
        out(__doc__.strip())
        return
    if a[0] == "setup":
        setup(a[1:], {})
        return
    if a[0] == "connect":
        rest = a[1:]
        if "--again" in rest:
            start_link(force=True)
        elif "--code" in rest:
            i = rest.index("--code")
            if i + 1 >= len(rest):
                fail('use: gmail connect --code "<code or redirected URL>"')
            finish_link(rest[i + 1])
        else:
            start_link()
        return
    if a[0] == "who":
        who()
        return

    sub = a[1] if len(a) > 1 and not a[1].startswith("--") else "list"
    rest = a[2:] if (len(a) > 1 and not a[1].startswith("--")) else a[1:]
    pos, flags = split_args(rest)
    if a[0] == "mail":
        if sub == "list":
            mail_list(pos, flags)
        elif sub == "read":
            mail_read(pos, flags)
        elif sub == "draft":
            mail_draft(pos, flags)
        elif sub == "send":
            mail_send(pos, flags)
        else:
            fail(f"unknown mail command \"{sub}\". Try gmail mail list/read/draft/send")
        return
    if a[0] in ("cal", "calendar"):
        if sub == "list":
            cal_list(pos, flags)
        elif sub == "add":
            cal_add(pos, flags)
        else:
            fail(f"unknown calendar command \"{sub}\". Try gmail cal list/add")
        return
    if a[0] == "contacts":
        if sub == "list":
            contacts_list(pos, flags)
        elif sub == "search":
            contacts_search(pos, flags)
        else:
            fail(f"unknown contacts command \"{sub}\". Try gmail contacts list/search")
        return
    if a[0] == "tasks":
        if sub in ("list", "lists"):
            tasks_list(pos, flags)
        elif sub == "add":
            tasks_add(pos, flags)
        elif sub == "done":
            tasks_done(pos, flags)
        else:
            fail(f"unknown tasks command \"{sub}\". Try gmail tasks list/add/done")
        return
    fail(f"unknown command \"{a[0]}\". Run `gmail` for what is possible.")


def split_args(args):
    pos, flags = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                flags[key] = args[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            pos.append(a)
            i += 1
    return pos, flags


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        fail(str(e))
    except KeyboardInterrupt:
        out("\ngmail: stopped")
        sys.exit(1)
