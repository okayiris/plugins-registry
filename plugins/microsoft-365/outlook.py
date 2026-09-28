#!/usr/bin/env python3
"""Microsoft 365 (Outlook) for Iris, through Microsoft Graph.

Read Outlook mail, make drafts and send them only after your approval, read the calendar and
make appointments, and read your contacts.

  outlook                          what is connected, and what still needs a link
  outlook connect                  start the sign-in (the app client id stays in the vault)
  outlook connect --finish         finish it, once you approved in the browser
  outlook connect --reset          forget the tokens and start a fresh sign-in
  outlook disconnect               forget the tokens

  outlook mail [--limit n] [--unread] [--folder <name>]
                                   the latest mail in a folder (default inbox, 10)
  outlook mail read <id>           one message, with its text
  outlook mail search "<query>" [--limit n]
                                   search all mail
  outlook mail draft --to <address> --subject "<subject>" --body "<text>"
          [--cc <address>] [--bcc <address>] [--html]
                                   make a draft in Outlook; nothing is sent yet
  outlook mail send <draft-id>     send exactly that stored draft
  outlook mail drafts              the drafts this command still holds

  outlook calendar [--days n]      coming appointments (default 7)
  outlook appointment --subject "<title>" --start <when> [--end <when>]
          [--location "<place>"] [--body "<text>"] [--online] [--all-day]
                                   make an appointment in the calendar
  outlook contacts [--search "<name>"] [--limit n]
                                   your contacts

  outlook timezone [<name>]        show or set the time zone used for appointments

Use your own Azure app registration (a public client, no secret). Put its client id in the
vault, never here:

  kluis vraag microsoft-365 --domein login.microsoftonline.com --auto "Azure app client id"

Then run `outlook connect` and approve in the browser. The sign-in uses the device code flow,
so the client id is only ever used inside the vault and never enters this command. Mail is
never sent by `outlook mail draft`; `outlook mail send` sends the exact stored text, and only
after you ask for it. `connect`, `mail draft`, `mail send` and `appointment` accept --dry-run
to show the request without calling Microsoft.
"""

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
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(HERE, ".state.json")

GRAPH = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
DEVICECODE = AUTHORITY + "/devicecode"
TOKEN = AUTHORITY + "/token"

SCOPES = [
    "offline_access",
    "User.Read",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Contacts.Read",
]

VAULT_ITEM = "microsoft-365"
VAULT_DOMAIN = "login.microsoftonline.com"
FORM = "Content-Type: application/x-www-form-urlencoded"
DRAFT_TTL = 7 * 24 * 3600

SETUP = """Microsoft 365 is not connected yet. To set it up:

1. Register an app in the Microsoft Entra admin center (https://entra.microsoft.com):
   App registrations -> New registration. Any name, and choose the account types you need.
   Under Authentication add the platform "Mobile and desktop applications" and switch
   "Allow public client flows" to Yes. No client secret is needed.

2. Under API permissions add these delegated permissions, then grant admin consent if your
   organization asks for it: User.Read, Mail.Read, Mail.ReadWrite, Mail.Send,
   Calendars.ReadWrite, Contacts.Read, offline_access.

3. Put the application (client) id in the vault (it is not a secret, so --auto is fine):

     kluis vraag microsoft-365 --domein login.microsoftonline.com --auto "Azure app client id"

4. Start the sign-in and approve it:

     outlook connect
     outlook connect --finish
"""


def fail(text):
    print("outlook: " + text)
    sys.exit(1)


# ---------------------------------------------------------------- state

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE)


# ---------------------------------------------------------------- the vault

def vault_bin():
    p = shutil.which("kluis") or shutil.which("vault")
    if p:
        return p
    p = os.path.expanduser("~/.local/bin/kluis")
    return p if os.path.isfile(p) else None


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
        names.append(re.split(r"\s{2,}", line)[0].strip())
    return names


def have_client():
    return VAULT_ITEM in vault_items()


def require_client():
    if not have_client():
        fail(f'no Azure app client id in the vault yet (I looked for "{VAULT_ITEM}").\n' + SETUP)


def vault_call(item, method, url, body=None, header=None):
    """Let the vault make the call, so the key never enters this process. Returns (status, text).

    A non-2xx answer is a normal result here (Microsoft reports a pending device code as 400),
    so the status line is read even when the vault command exits non-zero.
    """
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system")
    cmd = [exe, "doe", item, method, url]
    if body is not None:
        cmd.append(body)
    if header:
        cmd += ["--kop", header]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        fail("the vault did not answer in time")
    out = (proc.stdout or "").strip()
    first, _, rest = out.partition("\n")
    if first.startswith("status "):
        try:
            return int(first.split()[1]), rest.strip()
        except (IndexError, ValueError):
            pass
    msg = (proc.stderr or out).strip() or "the vault refused the call"
    for pre in ("kluis:", "vault:"):
        if msg.startswith(pre):
            msg = msg[len(pre):].strip()
    fail(msg)


# ---------------------------------------------------------------- http

def direct(method, url, headers=None, data=None, timeout=45):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except OSError as e:
        fail(f"cannot reach Microsoft ({e})")


def parse_json(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {}


def graph(method, path, token, params=None, body=None, extra_headers=None):
    url = GRAPH + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    return direct(method, url, headers, data)


def graph_error(status, text):
    d = parse_json(text)
    err = d.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or ""
        code = err.get("code") or ""
    else:
        msg = d.get("error_description") or (str(err) if err else "")
        code = str(err or "")
    if status == 401:
        return "Microsoft refused the token (401). Run `outlook connect --reset` to sign in again."
    if status == 403:
        return f"Microsoft refused this (403){': ' + msg if msg else ''}. " \
               "The app may miss a permission or admin consent; see the README."
    if status == 404:
        return "not found in this mailbox (404). Check the id."
    if status == 429:
        return "Microsoft is rate limiting (429). Try again in a moment."
    detail = msg or code or text[:300]
    return f"Microsoft returned {status}: {detail}"


def api(method, path, token, params=None, body=None, extra_headers=None):
    status, text = graph(method, path, token, params=params, body=body, extra_headers=extra_headers)
    if status >= 400:
        fail(graph_error(status, text))
    return parse_json(text) if text.strip() else {}


# ---------------------------------------------------------------- tokens

def refresh(st):
    rt = st.get("refresh_token")
    if not rt:
        fail("the sign-in has expired and there is no refresh token. Run `outlook connect` again.")
    body = ("client_id={g}&grant_type=refresh_token"
            f"&refresh_token={urllib.parse.quote(rt)}&scope={urllib.parse.quote(' '.join(SCOPES))}")
    status, text = vault_call(VAULT_ITEM, "POST", TOKEN, body=body, header=FORM)
    d = parse_json(text)
    if status != 200 or not d.get("access_token"):
        fail("the sign-in could not be refreshed: " +
             (d.get("error_description") or d.get("error") or text[:200]))
    st["access_token"] = d["access_token"]
    if d.get("refresh_token"):
        st["refresh_token"] = d["refresh_token"]
    st["expires_at"] = int(time.time()) + int(d.get("expires_in") or 3600)
    st["scope"] = d.get("scope") or st.get("scope")
    save_state(st)


def access_token():
    st = load_state()
    tok = st.get("access_token")
    if not tok:
        fail("not connected to Microsoft 365 yet.\n" + SETUP)
    exp = int(st.get("expires_at") or 0)
    if exp and time.time() > exp - 120:
        refresh(st)
        tok = load_state().get("access_token")
    return tok


def me(token):
    return api("GET", "/me", token,
               params={"$select": "displayName,userPrincipalName,mail"})


# ---------------------------------------------------------------- time helpers

def resolve_timezone(explicit=None):
    if explicit:
        return explicit
    st = load_state()
    if st.get("timezone"):
        return st["timezone"]
    env = os.environ.get("TZ")
    if env:
        return env
    try:
        with open("/etc/timezone", encoding="utf-8") as f:
            name = f.read().strip()
            if name:
                return name
    except OSError:
        pass
    return "UTC"


def parse_graph_dt(value):
    s = re.sub(r"\.\d+", "", str(value or ""))
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def local_text(value):
    dt = parse_graph_dt(value)
    if not dt:
        return str(value or "")
    if dt.tzinfo is None:
        # Graph already returned it in the time zone we asked for (calendar, events).
        return dt.strftime("%a %d %b %H:%M")
    try:
        from zoneinfo import ZoneInfo
        dt = dt.astimezone(ZoneInfo(resolve_timezone()))
    except Exception:
        pass
    return dt.strftime("%a %d %b %H:%M")


def parse_when(text):
    """A moment the owner typed. Returns a naive datetime in the chosen time zone."""
    t = str(text or "").strip()
    now = datetime.now()
    m = re.fullmatch(r"\+(\d+)\s*([hmd])", t, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        return now + timedelta(hours=n if unit == "h" else 0,
                               minutes=n if unit == "m" else 0,
                               days=n if unit == "d" else 0)
    m = re.fullmatch(r"(today|tomorrow)\s+(\d{1,2}):(\d{2})", t, re.I)
    if m:
        base = now if m.group(1).lower() == "today" else now + timedelta(days=1)
        return base.replace(hour=int(m.group(2)), minute=int(m.group(3)),
                            second=0, microsecond=0)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, fmt).replace(hour=9)
        except ValueError:
            continue
    fail(f'I cannot read the moment "{text}". Use 2026-09-30T14:00, 2026-09-30 14:00, '
         '"today 14:00", "tomorrow 09:30" or "+2h".')


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- argument helpers

def split_args(args):
    pos, opts = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            name = a[2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                opts[name] = args[i + 1]
                i += 2
            else:
                opts[name] = True
                i += 1
        else:
            pos.append(a)
            i += 1
    return pos, opts


def need(opts, name):
    value = opts.get(name)
    if not isinstance(value, str) or not value.strip():
        fail(f"--{name} is required")
    return value.strip()


def addresses(value):
    out = []
    for part in str(value or "").split(","):
        part = part.strip()
        if part:
            out.append({"emailAddress": {"address": part}})
    return out


def as_int(opts, name, default, low, high):
    value = opts.get(name)
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        fail(f"--{name} must be a number")
    return max(low, min(high, n))


# ---------------------------------------------------------------- connect

def cmd_connect(args):
    _, opts = split_args(args)
    st = load_state()

    if opts.get("dry-run"):
        print("Dry run: the vault would call")
        print(f"  POST {DEVICECODE}")
        print(f"  body: client_id={{g}}&scope={urllib.parse.quote(' '.join(SCOPES))}")
        print("and later POST " + TOKEN + " with grant_type=device_code.")
        return

    if opts.get("reset"):
        keep = {"timezone": st.get("timezone")} if st.get("timezone") else {}
        st = keep
        save_state(st)

    require_client()
    body = f"client_id={{g}}&scope={urllib.parse.quote(' '.join(SCOPES))}"
    status, text = vault_call(VAULT_ITEM, "POST", DEVICECODE, body=body, header=FORM)
    d = parse_json(text)
    if status != 200 or not d.get("device_code"):
        fail("the sign-in could not start: " +
             (d.get("error_description") or d.get("error") or text[:300]) +
             "\nCheck that the client id belongs to a public client with "
             '"Allow public client flows" switched on.')

    st["device_code"] = d["device_code"]
    st["user_code"] = d.get("user_code")
    st["verification_uri"] = d.get("verification_uri") or "https://microsoft.com/devicelogin"
    st["interval"] = int(d.get("interval") or 5)
    st["device_expires_at"] = int(time.time()) + int(d.get("expires_in") or 900)
    save_state(st)

    print("Open this page in a browser and sign in with your Microsoft account:")
    print("  " + st["verification_uri"])
    print(f'  code: {st["user_code"]}')
    print()
    print("Then finish here, within about 15 minutes:")
    print("  outlook connect --finish")


def cmd_connect_finish():
    st = load_state()
    device = st.get("device_code")
    if not device:
        fail("no sign-in is waiting. Run `outlook connect` first.")
    interval = max(int(st.get("interval") or 5), 5)
    deadline = int(st.get("device_expires_at") or 0) or int(time.time()) + 900

    print("Waiting for you to approve in the browser. Press Ctrl-C to stop.")
    while time.time() < deadline:
        body = ("client_id={g}"
                "&grant_type=urn:ietf:params:oauth:grant-type:device_code"
                f"&device_code={urllib.parse.quote(device)}")
        status, text = vault_call(VAULT_ITEM, "POST", TOKEN, body=body, header=FORM)
        d = parse_json(text)
        if status == 200 and d.get("access_token"):
            st["access_token"] = d["access_token"]
            if d.get("refresh_token"):
                st["refresh_token"] = d["refresh_token"]
            st["expires_at"] = int(time.time()) + int(d.get("expires_in") or 3600)
            st["scope"] = d.get("scope")
            for key in ("device_code", "user_code", "verification_uri", "interval",
                        "device_expires_at"):
                st.pop(key, None)
            save_state(st)
            who = me(st["access_token"])
            name = who.get("displayName") or who.get("userPrincipalName") or "your account"
            addr = who.get("mail") or who.get("userPrincipalName") or ""
            print(f"Connected as {name}" + (f" <{addr}>" if addr else "") + ".")
            return
        err = str(d.get("error") or "")
        if err == "authorization_pending":
            time.sleep(interval)
            continue
        if err == "slow_down":
            interval += 5
            time.sleep(interval)
            continue
        if err == "expired_token":
            fail("the code expired before it was approved. Run `outlook connect` again.")
        if err == "authorization_declined":
            fail("the sign-in was declined in the browser.")
        if status >= 400:
            fail("the sign-in failed: " +
                 (d.get("error_description") or d.get("error") or text[:300]))
        time.sleep(interval)
    fail("the code expired before it was approved. Run `outlook connect` again.")


def cmd_disconnect():
    st = load_state()
    for key in ("access_token", "refresh_token", "expires_at", "scope", "device_code",
                "user_code", "verification_uri", "interval", "device_expires_at"):
        st.pop(key, None)
    save_state(st)
    print("Disconnected. The stored drafts are kept; run `outlook connect` to link again.")


# ---------------------------------------------------------------- status

def cmd_status():
    st = load_state()
    if not st.get("access_token"):
        print(SETUP)
        return
    if not have_client():
        print(f'note: no client id found in the vault under "{VAULT_ITEM}".')
    who = me(access_token())
    name = who.get("displayName") or who.get("userPrincipalName") or "your account"
    addr = who.get("mail") or who.get("userPrincipalName") or ""
    print(f"Connected as {name}" + (f" <{addr}>" if addr else "") + ".")
    exp = int(st.get("expires_at") or 0)
    if exp:
        left = max(0, exp - int(time.time()))
        print(f"The access token is good for about {left // 60} more minutes "
              "(it refreshes itself when needed).")
    if st.get("scope"):
        print("Scopes: " + st["scope"])
    drafts = st.get("drafts") or {}
    if drafts:
        print(f"Drafts waiting for approval: {len(drafts)} "
              "(see `outlook mail drafts`).")


# ---------------------------------------------------------------- mail

def cmd_mail(args):
    pos, opts = split_args(args)
    sub = pos[0] if pos and not pos[0].startswith("-") else "inbox"

    if sub in ("inbox", "list", "search"):
        token = access_token()
        limit = as_int(opts, "limit", 10, 1, 100)
        folder = str(opts.get("folder") or "inbox")
        params = {
            "$top": limit,
            "$select": "id,from,subject,receivedDateTime,isRead,bodyPreview,webLink",
        }
        if sub == "search":
            query = " ".join(pos[1:]).strip() or need(opts, "query")
            params["$search"] = f'"{query}"'
            path = "/me/messages"
        else:
            if opts.get("unread"):
                params["$filter"] = "isRead eq false"
            params["$orderby"] = "receivedDateTime desc"
            path = "/me/messages" if folder.lower() in ("all", "alle") \
                else f"/me/mailFolders/{urllib.parse.quote(folder)}/messages"
        d = api("GET", path, token, params=params)
        rows = d.get("value") or []
        if not rows:
            print("No mail found.")
            return
        for m in rows:
            sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address") or "?"
            flag = "" if m.get("isRead") else "[unread] "
            print(f"{local_text(m.get('receivedDateTime'))}  {flag}{sender}")
            print(f"  {m.get('subject') or '(no subject)'}")
            print(f"  id: {m.get('id')}")
        return

    if sub == "read":
        if len(pos) < 2:
            fail("outlook mail read <id>")
        token = access_token()
        message_id = pos[1]
        d = api("GET", f"/me/messages/{urllib.parse.quote(message_id, safe='')}", token,
                params={"$select": "id,from,toRecipients,ccRecipients,subject,"
                                   "receivedDateTime,body,bodyPreview,webLink"},
                extra_headers={"Prefer": 'outlook.body-content-type="text"'})
        sender = ((d.get("from") or {}).get("emailAddress") or {}).get("address") or "?"
        print(f"From:    {sender}")
        to = ", ".join((r.get("emailAddress") or {}).get("address", "")
                       for r in (d.get("toRecipients") or []))
        if to:
            print(f"To:      {to}")
        cc = ", ".join((r.get("emailAddress") or {}).get("address", "")
                       for r in (d.get("ccRecipients") or []))
        if cc:
            print(f"Cc:      {cc}")
        print(f"Date:    {local_text(d.get('receivedDateTime'))}")
        print(f"Subject: {d.get('subject') or '(no subject)'}")
        print()
        body = (d.get("body") or {}).get("content") or d.get("bodyPreview") or ""
        print(body.strip()[:8000])
        if d.get("webLink"):
            print()
            print("In Outlook: " + d["webLink"])
        return

    if sub == "draft":
        to = need(opts, "to")
        subject = str(opts.get("subject") or "")
        body_text = str(opts.get("body") or "")
        html = bool(opts.get("html"))
        message = {
            "subject": subject,
            "body": {"contentType": "HTML" if html else "Text", "content": body_text},
            "toRecipients": addresses(to),
            "ccRecipients": addresses(opts.get("cc")),
            "bccRecipients": addresses(opts.get("bcc")),
        }
        if opts.get("dry-run"):
            print("Dry run: POST /me/messages")
            print(json.dumps(message, indent=2, ensure_ascii=False))
            return
        token = access_token()
        d = api("POST", "/me/messages", token, body=message)
        draft_id = secrets.token_hex(3)
        st = load_state()
        drafts = st.get("drafts") or {}
        drafts[draft_id] = {
            "graph_id": d.get("id"),
            "to": to,
            "cc": opts.get("cc") or "",
            "bcc": opts.get("bcc") or "",
            "subject": subject,
            "body": body_text,
            "html": html,
            "created": int(time.time()),
        }
        st["drafts"] = drafts
        save_state(st)
        print("Draft made in Outlook. Nothing has been sent.")
        print(f"  draft id: {draft_id}")
        print(f"  to:       {to}")
        print(f"  subject:  {subject or '(no subject)'}")
        print()
        print(f"To send exactly this text:  outlook mail send {draft_id}")
        return

    if sub == "send":
        if len(pos) < 2:
            fail("outlook mail send <draft-id>")
        draft_id = pos[1]
        st = load_state()
        draft = (st.get("drafts") or {}).get(draft_id)
        if not draft:
            fail(f"no draft with id {draft_id}. It may already have been sent; "
                 "make a new one with `outlook mail draft`.")
        message = {
            "subject": draft.get("subject") or "",
            "body": {"contentType": "HTML" if draft.get("html") else "Text",
                     "content": draft.get("body") or ""},
            "toRecipients": addresses(draft.get("to")),
            "ccRecipients": addresses(draft.get("cc")),
            "bccRecipients": addresses(draft.get("bcc")),
        }
        if opts.get("dry-run"):
            print(f"Dry run: would send draft {draft_id}")
            print(json.dumps(message, indent=2, ensure_ascii=False))
            return
        token = access_token()
        graph_id = draft.get("graph_id")
        if graph_id:
            status, text = graph("PATCH", f"/me/messages/{urllib.parse.quote(graph_id, safe='')}",
                                 token, body=message)
            if status < 400:
                status, text = graph("POST",
                                     f"/me/messages/{urllib.parse.quote(graph_id, safe='')}/send",
                                     token)
            else:
                status = 0
        else:
            status = 0
        if status < 200 or status >= 300:
            # The draft was gone or could not be sent as it was; send the stored text itself.
            api("POST", "/me/sendMail", token,
                body={"message": message, "saveToSentItems": True})
        drafts = st.get("drafts") or {}
        drafts.pop(draft_id, None)
        st["drafts"] = drafts
        save_state(st)
        print(f"Sent draft {draft_id} to {draft.get('to')}.")
        return

    if sub == "drafts":
        st = load_state()
        drafts = st.get("drafts") or {}
        if not drafts:
            print("No drafts waiting.")
            return
        for draft_id, draft in drafts.items():
            print(f"{draft_id}  to {draft.get('to')}  subject {draft.get('subject') or '(none)'}")
        print()
        print("Send one with:  outlook mail send <draft-id>")
        return

    fail(f'unknown mail command "{sub}". See `outlook --help`.')


# ---------------------------------------------------------------- calendar

def cmd_calendar(args):
    _, opts = split_args(args)
    days = as_int(opts, "days", 7, 1, 365)
    token = access_token()
    tz = resolve_timezone(opts.get("timezone") if isinstance(opts.get("timezone"), str) else None)
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    params = {
        "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "$top": 100,
        "$orderby": "start/dateTime",
        "$select": "id,subject,start,end,location,isAllDay,organizer,webLink,onlineMeeting",
    }
    d = api("GET", "/me/calendarView", token, params=params,
            extra_headers={"Prefer": f'outlook.timezone="{tz}"'})
    rows = d.get("value") or []
    if not rows:
        print(f"No appointments in the next {days} day(s).")
        return
    current = None
    for ev in rows:
        start = (ev.get("start") or {}).get("dateTime")
        day = (start or "")[:10]
        if day and day != current:
            current = day
            print()
            print(local_text(start).rsplit(" ", 1)[0] if start else day)
        subject = ev.get("subject") or "(no subject)"
        place = ((ev.get("location") or {}).get("displayName") or "").strip()
        when = "all day" if ev.get("isAllDay") else local_text(start)[-5:]
        line = f"  {when}  {subject}"
        if place:
            line += f"  @ {place}"
        print(line)
        if ev.get("onlineMeeting"):
            print("         online meeting")
    print()


def cmd_appointment(args):
    _, opts = split_args(args)
    subject = need(opts, "subject")
    start = parse_when(need(opts, "start"))
    end_raw = opts.get("end")
    end = parse_when(end_raw) if isinstance(end_raw, str) and end_raw.strip() \
        else start + timedelta(hours=1)
    if end <= start:
        fail("--end must be after --start")
    tz = resolve_timezone(opts.get("timezone") if isinstance(opts.get("timezone"), str) else None)
    event = {
        "subject": subject,
        "body": {"contentType": "Text", "content": str(opts.get("body") or "")},
        "start": {"dateTime": stamp(start), "timeZone": tz},
        "end": {"dateTime": stamp(end), "timeZone": tz},
    }
    if isinstance(opts.get("location"), str) and opts["location"].strip():
        event["location"] = {"displayName": opts["location"].strip()}
    if opts.get("online"):
        event["isOnlineMeeting"] = True
        event["onlineMeetingProvider"] = "teamsForBusiness"
    if opts.get("all-day"):
        event["isAllDay"] = True
    if opts.get("dry-run"):
        print("Dry run: POST /me/events")
        print(json.dumps(event, indent=2, ensure_ascii=False))
        return
    token = access_token()
    d = api("POST", "/me/events", token, body=event)
    print(f"Appointment made: {d.get('subject') or subject}")
    print(f"  from: {local_text((d.get('start') or {}).get('dateTime'))}")
    print(f"  to:   {local_text((d.get('end') or {}).get('dateTime'))}")
    if d.get("webLink"):
        print("  in Outlook: " + d["webLink"])
    print(f"  id: {d.get('id')}")


# ---------------------------------------------------------------- contacts

def cmd_contacts(args):
    _, opts = split_args(args)
    limit = as_int(opts, "limit", 25, 1, 200)
    token = access_token()
    params = {"$top": limit}
    search = opts.get("search")
    if isinstance(search, str) and search.strip():
        params["$search"] = f'"{search.strip()}"'
    else:
        params["$select"] = "displayName,emailAddresses,companyName,mobilePhone,businessPhones"
    d = api("GET", "/me/contacts", token, params=params)
    rows = d.get("value") or []
    if not rows:
        print("No contacts found.")
        return
    for c in rows:
        emails = ", ".join((e or {}).get("address", "")
                           for e in (c.get("emailAddresses") or []))
        phones = ", ".join(p for p in (c.get("mobilePhone"), *(c.get("businessPhones") or [])) if p)
        line = c.get("displayName") or "(no name)"
        if emails:
            line += f"  <{emails}>"
        if phones:
            line += f"  {phones}"
        if c.get("companyName"):
            line += f"  ({c['companyName']})"
        print(line)


# ---------------------------------------------------------------- timezone

def cmd_timezone(args):
    pos, _ = split_args(args)
    st = load_state()
    if not pos:
        print("Time zone: " + resolve_timezone())
        return
    name = pos[0]
    if "/" not in name and name.upper() != "UTC":
        fail("expecting an IANA name like Europe/Amsterdam")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
    except Exception:
        fail(f'"{name}" is not a known time zone')
    st["timezone"] = name
    save_state(st)
    print("Time zone set to " + name)


# ---------------------------------------------------------------- main

def main():
    args = sys.argv[1:]
    if not args:
        cmd_status()
        return
    cmd = args[0]
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
        return
    if cmd == "status":
        cmd_status()
    elif cmd == "connect":
        _, opts = split_args(args[1:])
        if opts.get("finish"):
            cmd_connect_finish()
        else:
            cmd_connect(args[1:])
    elif cmd == "disconnect":
        cmd_disconnect()
    elif cmd == "mail":
        cmd_mail(args[1:])
    elif cmd in ("calendar", "cal"):
        cmd_calendar(args[1:])
    elif cmd in ("appointment", "appointments"):
        cmd_appointment(args[1:])
    elif cmd in ("contacts", "contact"):
        cmd_contacts(args[1:])
    elif cmd == "timezone":
        cmd_timezone(args[1:])
    else:
        print(f'outlook: unknown command "{cmd}"\n')
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
