#!/usr/bin/env python3
"""mailbox: read the mailbox of this house. Read-only.

  mailbox                 the address, the open drafts and the latest sent mail
  mailbox inbox [n]       the last n received mails (default 10)
  mailbox sent [n]        the last n sent mails (default 10)
  mailbox read <id|n>     the full text of one mail, by id (a prefix is enough) or by inbox number

The command only reads. It never sends a mail and never makes or discards a draft.
Sending stays with `mail draft`, on the owner's screen.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = (os.environ.get("MAIL_URL") or "http://host.docker.internal:8790").rstrip("/")


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
    """An epoch (ms) or an ISO string, as YYYY-MM-DDTHH:MM, the same as the mail command."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        import datetime
        return datetime.datetime.utcfromtimestamp(value / 1000).strftime("%Y-%m-%dT%H:%M")
    text = str(value)
    return text[:16] if len(text) >= 16 else text


def one_line(text, width):
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 3] + "..."


def short_id(value):
    return str(value or "")[:8]


def overview():
    m = get("/mail")
    print(f"mailbox: {m.get('address', '')}")
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
            print(f"  {when(s.get('sentAt') or s.get('at'))}  to {addrs(s.get('to'))}  "
                  f"{one_line(s.get('subject'), 68)}  ({short_id(s.get('id'))})")
    print("use: mailbox inbox [n] | mailbox sent [n] | mailbox read <id|number>")


def list_inbox(n):
    mail = get(f"/mail/inbox?n={n}").get("mail", [])
    if not mail:
        print("inbox: no mail yet")
        return
    print(f"inbox: {len(mail)} mail")
    for i, x in enumerate(mail, 1):
        print(f"  [{i}] {when(x.get('at'))}  {x.get('from', '')}  "
              f"{one_line(x.get('subject'), 64)}  ({short_id(x.get('id'))})")


def list_sent(n):
    sent = get("/mail").get("sent", [])[:n]
    if not sent:
        print("sent: no mail yet")
        return
    print(f"sent: {len(sent)} mail")
    for s in sent:
        print(f"  {when(s.get('sentAt') or s.get('at'))}  to {addrs(s.get('to'))}  "
              f"{one_line(s.get('subject'), 68)}  ({short_id(s.get('id'))})")


def show(kind, x):
    if kind == "inbox":
        print(f"From: {x.get('from', '')}")
    print(f"To: {addrs(x.get('to'))}")
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
    text = x.get("text") or x.get("body") or ""
    print(text if str(text).strip() else "(no text)")


def read_mail(arg):
    arg = str(arg).strip()
    mail = get("/mail/inbox?n=200").get("mail", [])
    if arg.isdigit():
        i = int(arg)
        if 1 <= i <= len(mail):
            show("inbox", mail[i - 1])
            return
        sys.exit(f"mailbox: there is no inbox mail {arg}")
    all_mail = get("/mail")
    found = [("inbox", x) for x in mail]
    found += [("draft", d) for d in all_mail.get("drafts", [])]
    found += [("sent", s) for s in all_mail.get("sent", [])]
    hits = [(kind, x) for kind, x in found if str(x.get("id", "")).startswith(arg)]
    if not hits:
        sys.exit(f"mailbox: no mail with id {arg}")
    if len(hits) > 1:
        sys.exit(f"mailbox: id {arg} is not unique, give more characters")
    show(hits[0][0], hits[0][1])


def count(value, default=10):
    if value is None:
        return default
    if not str(value).isdigit() or int(value) < 1:
        sys.exit("mailbox: give a number of mails, like 10")
    return min(int(value), 200)


def main(argv):
    if not argv:
        overview()
    elif argv[0] == "inbox":
        list_inbox(count(argv[1] if len(argv) > 1 else None))
    elif argv[0] == "sent":
        list_sent(count(argv[1] if len(argv) > 1 else None))
    elif argv[0] == "read" and len(argv) > 1:
        read_mail(argv[1])
    else:
        print(__doc__.strip())
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
