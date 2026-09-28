#!/usr/bin/env python3
"""mailbox: read the mailbox of this house. Read-only.

  mailbox                 the address, the latest received mail, the open drafts, the latest sent mail
                          and, with the calendar plugin, what is coming up
  mailbox inbox [n]       the last n received mails (default 10)
  mailbox sent [n]        the last n sent mails (default 10)
  mailbox read <id|n>     the full text of one mail, by id (a prefix is enough) or by inbox number
  mailbox agenda          the coming meetings and the invitations in the mail (needs the calendar plugin)
  mailbox accept <id>     put the invitation in that mail in the calendar (needs the calendar plugin)

The command only reads mail. It never sends a mail and never makes or discards a draft.
Sending stays with `mail draft`, on the owner's screen. `agenda` and `accept` hand over to `calendar`.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

BASE = (os.environ.get("MAIL_URL") or os.environ.get("IRIS_BRIDGE_URL")
        or "http://host.docker.internal:8790").rstrip("/")
AS_JSON = "--json" in sys.argv


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit("mailbox: this house has no mailbox")
        sys.exit(f"mailbox: the bridge answered HTTP {e.code}")
    except OSError as e:
        sys.exit(f"mailbox: the bridge is not reachable ({e})")


def addrs(value):
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    return str(value or "")


def when(value):
    """An epoch (ms) or an ISO string, as YYYY-MM-DD HH:MM in the house's own time, like the window."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)):
            moment = datetime.datetime.fromtimestamp(value / 1000)
        else:
            moment = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if moment.tzinfo:
                moment = moment.astimezone().replace(tzinfo=None)
        return moment.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OverflowError, OSError):
        return str(value)[:16]


def one_line(text, width):
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 3] + "..."


def short_id(value):
    return str(value or "")[:8]


def invitation_in(x):
    """Whether a mail carries a calendar invitation: an .ics in its text or as an attachment."""
    parts = [x.get("text"), x.get("body"), x.get("ics")]
    for a in x.get("attachments") or []:
        if isinstance(a, dict):
            kind = str(a.get("type") or a.get("contentType") or "").lower()
            name = str(a.get("name") or a.get("filename") or "").lower()
            if "calendar" in kind or name.endswith(".ics"):
                return True
    return any(isinstance(p, str) and "BEGIN:VCALENDAR" in p for p in parts)


def readable(text):
    """The text of a mail without the raw invitation code some mail programs put in it."""
    text = re.sub(r"BEGIN:VCALENDAR.*?(END:VCALENDAR|$)", "[calendar invitation]", str(text or ""), flags=re.S)
    return text.strip()


# --- the calendar plugin, when the house has it ----------------------------------------------------

def calendar(args):
    """Run the calendar plugin's command; None when it is not installed (or not switched on)."""
    if not shutil.which("calendar"):
        return None
    try:
        p = subprocess.run(["calendar"] + args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": f"the calendar did not answer ({e})"}
    out = p.stdout.strip() or p.stderr.strip()
    if "--json" not in args:
        return {"code": p.returncode, "text": out}
    try:
        return json.loads(out)
    except ValueError:
        return {"error": out or "the calendar did not answer"}


def agenda_data():
    week = calendar(["week", "7", "--json"])
    if week is None:
        return {"installed": False, "meetings": [], "invites": []}
    if week.get("error"):
        return {"installed": True, "error": week["error"], "meetings": [], "invites": []}
    now = calendar(["--json"]) or {}
    return {"installed": True, "today": week.get("today", ""), "meetings": week.get("meetings", []),
            "invites": now.get("invites", []), "mailNote": now.get("mailNote", "")}


def meeting_line(m):
    place = f" at {m['place']}" if m.get("place") else ""
    return f"  {m['starts'][:10]} {m['starts'][11:16]}-{m['ends'][11:16]}  {m['title']}{place}  [{m['id']}]"


def agenda_lines(data, limit):
    if not data["installed"]:
        return []
    if data.get("error"):
        return [f"calendar: {data['error']}"]
    lines = []
    meetings = data["meetings"]
    if meetings:
        lines.append(f"coming up ({min(limit, len(meetings))} of {len(meetings)} in the next 7 days):"
                     if len(meetings) > limit else "coming up (next 7 days):")
        lines += [meeting_line(m) for m in meetings[:limit]]
    else:
        lines.append("coming up: nothing planned in the next 7 days")
    todo = [x for x in data["invites"] if x.get("state") in ("new", "changed")]
    for x in todo:
        lines.append(f"  invitation not in the calendar yet: {x['title']}, {x['starts'][:10]} {x['starts'][11:16]}"
                     f"  (mailbox accept {short_id(x.get('mailId'))})")
    return lines


# --- commands -------------------------------------------------------------------------------------

def sent_line(s):
    return (f"  {when(s.get('sentAt') or s.get('at'))}  to {addrs(s.get('to'))}  "
            f"{one_line(s.get('subject'), 68)}  ({short_id(s.get('id'))})")


def inbox_line(i, x):
    mark = "  [invitation]" if invitation_in(x) else ""
    return (f"  [{i}] {when(x.get('at'))}  {x.get('from', '')}  "
            f"{one_line(x.get('subject'), 64)}  ({short_id(x.get('id'))}){mark}")


def overview():
    m = get("/mail")
    print(f"mailbox: {m.get('address', '')}")
    inbox = get("/mail/inbox?n=3").get("mail", [])
    if inbox:
        print("latest received:")
        for i, x in enumerate(inbox, 1):
            print(inbox_line(i, x))
    else:
        print("received: none")
    drafts = m.get("drafts", [])
    if drafts:
        print(f"open drafts: {len(drafts)}")
        for d in drafts:
            print(f"  draft {short_id(d.get('id'))}  to {addrs(d.get('to'))}  {one_line(d.get('subject'), 64)}")
    else:
        print("open drafts: none")
    sent = m.get("sent", [])
    if not sent:
        print("sent: none")
    else:
        shown = sent[:5]
        extra = f" of {len(sent)}" if len(sent) > len(shown) else ""
        print(f"latest sent ({len(shown)}{extra}):")
        for s in shown:
            print(sent_line(s))
    for line in agenda_lines(agenda_data(), 3):
        print(line)
    print("use: mailbox inbox [n] | mailbox sent [n] | mailbox read <id|number>")


def list_inbox(n):
    mail = get(f"/mail/inbox?n={n}").get("mail", [])
    if not mail:
        print("inbox: no mail yet")
        return
    print(f"inbox: {len(mail)} mail")
    for i, x in enumerate(mail, 1):
        print(inbox_line(i, x))


def list_sent(n):
    sent = get("/mail").get("sent", [])[:n]
    if not sent:
        print("sent: no mail yet")
        return
    print(f"sent: {len(sent)} mail")
    for s in sent:
        print(sent_line(s))


def show(kind, x):
    if kind == "inbox":
        print(f"From: {x.get('from', '')}")
    if addrs(x.get("to")):
        print(f"To: {addrs(x.get('to'))}")
    if when(x.get("sentAt") or x.get("at")):
        print(f"Date: {when(x.get('sentAt') or x.get('at'))}")
    print(f"Subject: {x.get('subject', '')}")
    print(f"Id: {x.get('id', '')}")
    if kind == "sent":
        if x.get("maillogId"):
            print(f"Sent through Maillog: {x['maillogId']}")
        print()
        print("This house keeps no text for sent mail; the bridge stores only when it went and to whom.")
        return
    if kind == "draft":
        print("State: draft, not sent")
    print()
    text = readable(x.get("text") or x.get("body") or "")
    print(text if text else "(no text)")
    if kind == "inbox" and invitation_in(x):
        print()
        if shutil.which("calendar"):
            print(f"This mail carries a calendar invitation. To put it in the calendar: mailbox accept {short_id(x.get('id'))}")
        else:
            print("This mail carries a calendar invitation. With the calendar plugin it can go in the calendar.")


def find(arg, inbox_only=False):
    arg = str(arg).strip()
    mail = get("/mail/inbox?n=200").get("mail", [])
    if arg.isdigit() and len(arg) <= 3:  # an inbox number (at most 200); a longer number is an id
        i = int(arg)
        if 1 <= i <= len(mail):
            return "inbox", mail[i - 1]
        sys.exit(f"mailbox: there is no inbox mail {arg}")
    found = [("inbox", x) for x in mail]
    if not inbox_only:
        all_mail = get("/mail")
        found += [("draft", d) for d in all_mail.get("drafts", [])]
        found += [("sent", s) for s in all_mail.get("sent", [])]
    hits = [(kind, x) for kind, x in found if arg and str(x.get("id", "")).startswith(arg)]
    if not hits:
        sys.exit(f"mailbox: no mail with id {arg}")
    if len(hits) > 1:
        sys.exit(f"mailbox: id {arg} is not unique, give more characters")
    return hits[0]


def read_mail(arg):
    show(*find(arg))


def agenda():
    data = agenda_data()
    if AS_JSON:
        print(json.dumps(data))
        return
    if not data["installed"]:
        sys.exit("mailbox: the calendar plugin is not installed; with it, the meetings show here")
    for line in agenda_lines(data, 50):
        print(line)


def accept(arg):
    kind, x = find(arg, inbox_only=True)
    if not invitation_in(x):
        sys.exit(f"mailbox: mail {short_id(x.get('id'))} carries no calendar invitation")
    answer = calendar(["accept", str(x.get("id")), "--json"] if AS_JSON else ["accept", str(x.get("id"))])
    if answer is None:
        sys.exit("mailbox: the calendar plugin is not installed, so there is no calendar to put it in")
    if AS_JSON:
        print(json.dumps(answer))
        if answer.get("error"):
            sys.exit(1)
        return
    print(answer["text"])
    if answer["code"]:
        sys.exit(answer["code"])


def count(value, default=10):
    if value is None:
        return default
    if not str(value).isdigit() or int(value) < 1:
        sys.exit("mailbox: give a number of mails, like 10")
    return min(int(value), 200)


def main(argv):
    argv = [a for a in argv if a != "--json"]
    if not argv:
        overview()
    elif argv[0] == "inbox":
        list_inbox(count(argv[1] if len(argv) > 1 else None))
    elif argv[0] == "sent":
        list_sent(count(argv[1] if len(argv) > 1 else None))
    elif argv[0] == "read" and len(argv) > 1:
        read_mail(argv[1])
    elif argv[0] == "agenda":
        agenda()
    elif argv[0] == "accept" and len(argv) > 1:
        accept(argv[1])
    else:
        print(__doc__.strip())
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
