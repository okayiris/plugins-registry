#!/usr/bin/env python3
"""Maillog for Iris: send transactional mail and read what Maillog did with it.

  maillog send --to <address> --subject <subject> --body <text> [--from <address>]
       Show the message and stop. Nothing is sent until you confirm it.
  maillog send --confirm <id>
       Send the message shown under that id (kept for one hour).
  maillog events [--limit <n>]      recent messages with their delivery status
  maillog logs [--limit <n>]        every API call Maillog handled, newest first
  maillog stats [--days <n>]        daily numbers (7, 30 or 90 days)
  maillog key                       is there a key, and which vault item
  maillog key ask                   let the owner paste the key in the vault

Sending mail is an explicit act of the owner and it reaches other people, so
`maillog send` first prints the message as a draft; only `maillog send --confirm
<id>` really sends it. Events, logs and stats only read.

The API key never enters this tool: the vault makes each call with
`kluis doe maillog-api ...` and keeps the value. Nothing is written to disk except
drafts you have not confirmed yet, inside this plugin folder.

Endpoints and fields come from https://maillog.dev/docs: POST /v1/emails,
GET /v1/emails, GET /v1/logs and GET /v1/metrics.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(HERE, ".state.json")
CONFIG = os.path.join(HERE, "config.json")
API = "https://api.maillog.dev/v1"
VAULT_ITEM = "maillog-api"
VAULT_DOMAIN = "maillog.dev"
DRAFT_TTL = 3600
DEFAULT_LIMIT = 10

SEND_USAGE = ("maillog send --to <address> --subject <subject> --body <text> "
              "[--from <address>]")


def fail(text):
    print("maillog: " + text)
    sys.exit(1)


# ---------------------------------------------------------------- small files

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp, STATE)


def default_from():
    return str(load_json(CONFIG).get("from") or "").strip()


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


def have_key():
    return VAULT_ITEM in vault_items()


def require_key():
    if not have_key():
        fail(f'no Maillog key in the vault yet (I looked for "{VAULT_ITEM}"). '
             "Run `maillog key ask` once; the vault asks you to paste it, "
             "and this tool never sees it.")


def redact(text):
    return re.sub(r"ma_[A-Za-z0-9_-]{4,}", "ma_***", str(text))


def vault_call(method, path, body=None):
    """Let the vault make the call, so the key never enters this process.
    Returns (status, text)."""
    require_key()
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system")
    url = API + path
    cmd = [exe, "doe", VAULT_ITEM, method, url]
    if body is not None:
        cmd.append(body if isinstance(body, str) else json.dumps(body))
    cmd += ["--kop", "Authorization: Bearer {g}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        fail("Maillog did not answer in time")
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
    fail(redact(msg))


# ---------------------------------------------------------------- the API

def maillog_error(status, text):
    data = {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            data = parsed
    except (ValueError, TypeError):
        data = {}
    name = str(data.get("name") or data.get("error") or "").strip()
    message = str(data.get("message") or "").strip()
    if not message and isinstance(data.get("errors"), list):
        message = "; ".join(str(e) for e in data["errors"][:5])
    if status == 401:
        return ("Maillog did not accept the request (401 unauthorized, a missing or "
                "malformed key). Put a fresh key in the vault with `maillog key ask`.")
    if status == 403 and name == "from_not_allowed":
        return ("Maillog refused the sender (403 from_not_allowed): that address is not "
                "on a domain verified for sending. Add and verify the domain in the "
                "Maillog dashboard, or send from an address that is.")
    if status == 403 and name == "sandbox_restricted":
        return ("This is a sandbox key, and it may only send to the address it was "
                "issued for (403 sandbox_restricted).")
    if status == 403:
        return ("Maillog refused the key (403 forbidden): it may be invalid, revoked or "
                "expired. Put a fresh one with `maillog key ask`.")
    if status == 422:
        return ("Maillog rejected the values (422 validation_error)"
                + (": " + message if message else "."))
    if status == 429:
        return ("Maillog is rate limiting (429)"
                + (": " + message if message else ". Wait a moment and try again."))
    return "Maillog returned " + str(status) + (": " + message if message else ".")


def api_json(method, path, body=None):
    status, text = vault_call(method, path, body)
    if status >= 400:
        fail(maillog_error(status, text))
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        fail("Maillog answered with something that is not JSON: " + redact(text)[:200])


# ---------------------------------------------------------------- showing answers

LIST_KEYS = ("data", "items", "results", "emails", "logs", "events", "metrics",
             "records", "messages")


def unwrap(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]
    return []


def field(item, *names):
    if not isinstance(item, dict):
        return None
    for name in names:
        value = item.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def short(value, limit=90):
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if len(text) <= limit else text[:limit - 3] + "..."


def stamp(item):
    return field(item, "created_at", "created", "timestamp", "time", "date", "at",
                 "inserted_at")


def render_event(item):
    subject = field(item, "subject")
    to = field(item, "to", "recipient", "email", "address")
    if isinstance(to, list):
        to = ", ".join(str(x) for x in to)
    status = field(item, "status", "state", "event", "type", "last_event")
    title = short(subject) if subject else (short(status) if status else "message")
    if to:
        title += " -> " + short(to)
    lines = [title]
    bits = []
    if status:
        bits.append(str(status))
    for key, lab in (("opens", "opens"), ("open_count", "opens"),
                     ("clicks", "clicks"), ("click_count", "clicks")):
        if item.get(key) not in (None, ""):
            bits.append(f"{lab} {item[key]}")
    when = stamp(item)
    if when:
        bits.append(short(when, 30))
    if bits:
        lines.append("   " + " | ".join(bits))
    mid = field(item, "id", "message_id", "uuid")
    if mid:
        lines.append("   id " + str(mid))
    return lines


def render_log(item):
    method = field(item, "method", "verb")
    path = field(item, "path", "endpoint", "route", "url")
    code = field(item, "status", "status_code", "statusCode", "code")
    title = " ".join(str(x) for x in (method, path) if x) or short(
        field(item, "event", "type") or "call")
    lines = [short(title)]
    bits = []
    if code not in (None, ""):
        bits.append("status " + str(code))
    when = stamp(item)
    if when:
        bits.append(short(when, 30))
    if bits:
        lines.append("   " + " | ".join(bits))
    return lines


def render_generic(item):
    if not isinstance(item, dict):
        return [short(item)]
    scalars = [(k, v) for k, v in item.items()
               if isinstance(v, (str, int, float, bool)) and str(v) != ""]
    if not scalars:
        return [short(json.dumps(item))]
    lines = [f"{k}: {short(v, 60)}" for k, v in scalars[:6]]
    return lines


def show(items, kind):
    if not items:
        return False
    lines = []
    for index, item in enumerate(items, 1):
        if kind == "events":
            block = render_event(item)
        elif kind == "logs":
            block = render_log(item)
        else:
            block = render_generic(item)
        if not block:
            continue
        lines.append(f"{index}. {block[0]}")
        lines.extend(block[1:])
    print("\n".join(lines))
    return True


# ---------------------------------------------------------------- commands

def parse_args(args, valued=()):
    out = {"rest": []}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-h", "--help"):
            print(__doc__.strip())
            sys.exit(0)
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if key not in valued:
                fail(f"unknown option {arg}")
            if i + 1 >= len(args):
                fail(f"{arg} needs a value")
            out[key] = args[i + 1]
            i += 2
        else:
            out["rest"].append(arg)
            i += 1
    return out


def pos_int(value, default, name, cap=200):
    if value in (None, ""):
        return default
    try:
        number = int(str(value).strip())
    except ValueError:
        fail(f"{name} must be a whole number")
    if number < 1:
        fail(f"{name} must be at least 1")
    return min(number, cap)


def confirm_send(draft_id):
    state = load_json(STATE)
    drafts = state.get("drafts") if isinstance(state.get("drafts"), dict) else {}
    draft = drafts.get(draft_id)
    if not isinstance(draft, dict):
        fail(f"no message is waiting under id {draft_id}; it may already have been "
             "sent, or it expired.")
    if time.time() - float(draft.get("at", 0)) > DRAFT_TTL:
        drafts.pop(draft_id, None)
        state["drafts"] = drafts
        save_state(state)
        fail(f"the message under id {draft_id} has expired; make it again with "
             "`maillog send`.")
    payload = {
        "from": draft["from"],
        "to": [draft["to"]],
        "subject": draft["subject"],
        "text": draft["body"],
    }
    data = api_json("POST", "/emails", payload)
    drafts.pop(draft_id, None)
    state["drafts"] = drafts
    save_state(state)
    message_id = None
    if isinstance(data, dict):
        message_id = data.get("id") or data.get("message_id")
    line = "Maillog accepted the message"
    if message_id:
        line += f" (id {message_id})"
    print(line + f" for {draft['to']}. Delivery is now on Maillog's side.")


def cmd_send(args):
    confirm = args.get("confirm")
    if confirm:
        confirm_send(str(confirm).strip())
        return
    to = str(args.get("to") or "").strip()
    subject = str(args.get("subject") or "").strip()
    body = args.get("body")
    sender = str(args.get("from") or "").strip() or default_from()
    missing = [name for name, value in (("--to", to), ("--subject", subject),
                                        ("--body", body)) if not str(value or "").strip()]
    if missing:
        fail("send needs " + ", ".join(missing) + ". Usage: " + SEND_USAGE)
    if not sender:
        fail('no sender address: pass --from <address> or set "from" in config.json')
    draft_id = secrets.token_hex(4)
    state = load_json(STATE)
    drafts = state.get("drafts") if isinstance(state.get("drafts"), dict) else {}
    now = time.time()
    drafts = {k: v for k, v in drafts.items()
              if isinstance(v, dict) and now - float(v.get("at", 0)) < DRAFT_TTL}
    drafts[draft_id] = {"to": to, "subject": subject, "body": body,
                        "from": sender, "at": now}
    state["drafts"] = drafts
    save_state(state)
    print(f"Draft {draft_id}. Nothing has been sent yet.")
    print(f"  From:    {sender}")
    print(f"  To:      {to}")
    print(f"  Subject: {subject}")
    for line in str(body).splitlines() or [""]:
        print("  | " + line)
    print()
    print(f"This reaches {to}. To really send it, run:")
    print(f"  maillog send --confirm {draft_id}")
    print("The draft is kept for one hour.")


def cmd_events(limit):
    query = urllib.parse.urlencode({"limit": limit})
    data = api_json("GET", "/emails?" + query)
    items = unwrap(data)[:limit]
    if not show(items, "events"):
        print("Maillog has no messages to show yet.")


def cmd_logs(limit):
    query = urllib.parse.urlencode({"limit": limit})
    data = api_json("GET", "/logs?" + query)
    items = unwrap(data)[:limit]
    if not show(items, "logs"):
        print("Maillog has no API calls to show yet.")


def cmd_stats(days):
    query = urllib.parse.urlencode({"days": days})
    data = api_json("GET", "/metrics?" + query)
    items = unwrap(data)
    if not show(items, "stats"):
        print(f"Maillog has no numbers for the last {days} days.")


def cmd_key(rest):
    if rest and rest[0] in ("ask", "vraag"):
        exe = vault_bin()
        if not exe:
            fail("the vault command (kluis) is not on this system")
        try:
            proc = subprocess.run(
                [exe, "vraag", VAULT_ITEM, "--domein", VAULT_DOMAIN,
                 "Maillog API key (full access, so this plugin can send and read)",
                 "--kop", "Authorization: Bearer {g}"],
                capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            fail("the vault prompt did not finish in time")
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            fail(err or out or "the vault did not store a key")
        print(out or f'Maillog key stored in the vault as "{VAULT_ITEM}".')
        return
    if have_key():
        print(f'Maillog key is in the vault as "{VAULT_ITEM}".')
    else:
        print("No Maillog key yet. Run `maillog key ask` once; the vault asks you "
              "to paste it, and this tool never sees it.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip())
        return
    command = args[0].lower()
    rest = args[1:]
    if command == "send":
        cmd_send(parse_args(rest, valued=("to", "subject", "body", "from", "confirm")))
    elif command == "events":
        parsed = parse_args(rest, valued=("limit",))
        cmd_events(pos_int(parsed.get("limit"), DEFAULT_LIMIT, "--limit"))
    elif command == "logs":
        parsed = parse_args(rest, valued=("limit",))
        cmd_logs(pos_int(parsed.get("limit"), DEFAULT_LIMIT, "--limit"))
    elif command == "stats":
        parsed = parse_args(rest, valued=("days",))
        cmd_stats(pos_int(parsed.get("days"), 7, "--days", cap=90))
    elif command == "key":
        cmd_key(rest)
    elif command in ("help", "-h", "--help"):
        print(__doc__.strip())
    else:
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nmaillog: stopped")
        sys.exit(1)
