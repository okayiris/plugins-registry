#!/usr/bin/env python3
"""calendar: the meetings of this house, planned here or taken over from invitations in the mailbox.

  calendar                                today and tomorrow, and invitations waiting in the mailbox
  calendar week [days]                    the days ahead (7 by default)
  calendar search <text>                  on title, place, note or guest, in the next 365 days
  calendar show <id>                      one meeting in full
  calendar meet "<title>" <date> <time> [--minutes 60] [--with a@x.nl,b@y.nl] [--where <place>] [--note <text>]
                                          plan a meeting; prints the invitation, ready as a mail draft
  calendar move <id> <date> <time> [--minutes N]
                                          move it; prints the update for the guests
  calendar cancel <id>                    cancel it; prints the cancellation for the guests
  calendar invitation <id>                the invitation of a meeting again, as a mail draft
  calendar invites                        invitations in the mailbox, and whether they are in the calendar
  calendar accept <n|mail id>             put invitation n (from `calendar invites`) in the calendar
  calendar ics <id>                       the meeting as an .ics file (iCalendar)

A date is today, tomorrow, a weekday (monday, next monday), 2026-10-01 or 1-10. A time is 14:30 or 14.
Add --json to any of them for the window. The command never sends a mail: an invitation goes out as a
draft through the house's `mail draft`, and the owner presses Send.
"""
import datetime
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
DB = os.path.join(HERE, "data.db")
SCHEMA = os.path.join(HERE, "schema.sql")
BRIDGE = (os.environ.get("MAIL_URL") or os.environ.get("IRIS_BRIDGE_URL")
          or "http://host.docker.internal:8790").rstrip("/")

AS_JSON = "--json" in sys.argv
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3, "vrijdag": 4, "zaterdag": 5, "zondag": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "ma": 0, "di": 1, "wo": 2, "do": 3, "vr": 4, "za": 5, "zo": 6,
}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class Stop(Exception):
    """A plain answer that ends the command with exit code 1."""


def fail(message):
    raise Stop(message)


# --- the database ---------------------------------------------------------------------------------

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    # The house makes data.db from schema.sql on enable; a folder copied in by hand gets it here.
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    return con


def meeting(row):
    return {
        "id": row["id"], "uid": row["uid"], "title": row["title"], "starts": row["starts"], "ends": row["ends"],
        "place": row["place"], "note": row["note"], "guests": split_addresses(row["guests"]),
        "organizer": row["organizer"], "source": row["source"], "mailId": row["mail_id"],
        "sequence": row["sequence"], "status": row["status"],
    }


def by_id(con, value):
    if not str(value).isdigit():
        fail(f"calendar: {value} is not a meeting number; `calendar week` shows them")
    row = con.execute("SELECT * FROM meetings WHERE id = ?", (int(value),)).fetchone()
    if not row:
        fail(f"calendar: there is no meeting {value}")
    return meeting(row)


def between(con, start, end):
    rows = con.execute("SELECT * FROM meetings WHERE status = 'confirmed' AND ends > ? AND starts < ? "
                       "ORDER BY starts, id", (stamp(start), stamp(end))).fetchall()
    return [meeting(r) for r in rows]


# --- time -----------------------------------------------------------------------------------------

def now():
    return datetime.datetime.now().replace(second=0, microsecond=0)


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


def parse_stamp(text):
    return datetime.datetime.strptime(text[:16], "%Y-%m-%dT%H:%M")


def parse_date(words):
    """A date from one or two words (`next monday`). Returns (date, words used)."""
    today = now().date()
    first = words[0].lower() if words else ""
    if first in ("next", "volgende") and len(words) > 1 and words[1].lower() in WEEKDAYS:
        ahead = (WEEKDAYS[words[1].lower()] - today.weekday()) % 7 or 7
        return today + datetime.timedelta(days=ahead), 2
    if first in ("today", "vandaag"):
        return today, 1
    if first in ("tomorrow", "morgen"):
        return today + datetime.timedelta(days=1), 1
    if first in ("overmorgen",):
        return today + datetime.timedelta(days=2), 1
    if first in WEEKDAYS:
        return today + datetime.timedelta(days=(WEEKDAYS[first] - today.weekday()) % 7), 1
    rolls = False
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", first)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})(?:[-/](\d{4}))?", first)
        if not m:
            fail(f"calendar: {words[0] if words else 'nothing'} is not a date; say today, tomorrow, "
                 "a weekday, 2026-10-01 or 1-10")
        d, mo = int(m[1]), int(m[2])
        y = int(m[3]) if m[3] else today.year
        rolls = not m[3]
    try:
        day = datetime.date(y, mo, d)
        if rolls and day < today:
            day = day.replace(year=y + 1)  # 1-2 in December is next February
    except ValueError:
        fail(f"calendar: {words[0]} is not a day on the calendar")
    return day, 1


def parse_time(word):
    m = re.fullmatch(r"(\d{1,2})(?:[:.h](\d{2}))?", str(word or "").lower())
    if not m or int(m[1]) > 23 or int(m[2] or 0) > 59:
        fail(f"calendar: {word or 'nothing'} is not a time; say 14:30 or 14")
    return datetime.time(int(m[1]), int(m[2] or 0))


def day_label(day):
    today = now().date()
    if day == today:
        return "Today"
    if day == today + datetime.timedelta(days=1):
        return "Tomorrow"
    return f"{DAY_NAMES[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def when_text(m):
    s, e = parse_stamp(m["starts"]), parse_stamp(m["ends"])
    end = e.strftime("%H:%M") if e.date() == s.date() else f"{day_label(e.date())} {e:%H:%M}"
    return f"{day_label(s.date())} {s:%H:%M}-{end}"


# --- options --------------------------------------------------------------------------------------

def options(args, known):
    """Split `--name value` options from the words; --json has no value."""
    words, opts = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            i += 1
            continue
        if a.startswith("--"):
            name = a[2:]
            if name not in known:
                fail(f"calendar: --{name} is not an option here ({', '.join('--' + k for k in known)})")
            if i + 1 >= len(args):
                fail(f"calendar: --{name} needs a value")
            opts[name] = args[i + 1]
            i += 2
            continue
        words.append(a)
        i += 1
    return words, opts


def split_addresses(text):
    return [a for a in (x.strip() for x in re.split(r"[,;\s]+", str(text or ""))) if a]


def check_addresses(values):
    for a in values:
        if not re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", a):
            fail(f"calendar: {a} is not a mail address")
    return values


def minutes_of(value, default):
    if value is None:
        return default
    if not str(value).isdigit() or not 5 <= int(value) <= 24 * 60:
        fail("calendar: --minutes is a number between 5 and 1440")
    return int(value)


# --- the mailbox of this house --------------------------------------------------------------------

def bridge(path):
    try:
        with urllib.request.urlopen(BRIDGE + path, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            fail("calendar: this house has no mailbox, so there are no invitations to read")
        fail(f"calendar: the mailbox answered HTTP {e.code}")
    except (OSError, ValueError) as e:
        fail(f"calendar: the mailbox is not reachable ({e})")


def house_address():
    """This house's own mail address, the organizer of what it plans. Planning works without it."""
    try:
        with urllib.request.urlopen(BRIDGE + "/mail", timeout=10) as r:
            return str(json.load(r).get("address") or "")
    except (OSError, ValueError):
        return ""


# --- iCalendar ------------------------------------------------------------------------------------

def ics_escape(text):
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_unescape(text):
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m[1] in "nN" else m[1], text)


def fold(line):
    """Lines of at most 75 octets, continued with a space (RFC 5545 3.1)."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut and (raw[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n ".join(out)


def utc(text):
    return parse_stamp(text).astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ics(m, method="REQUEST"):
    status = "CANCELLED" if method == "CANCEL" else "CONFIRMED"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Iris//calendar plugin//EN", f"METHOD:{method}",
             "BEGIN:VEVENT", f"UID:{m['uid']}", f"SEQUENCE:{m['sequence']}",
             f"DTSTAMP:{now().astimezone(datetime.timezone.utc):%Y%m%dT%H%M%SZ}",
             f"DTSTART:{utc(m['starts'])}", f"DTEND:{utc(m['ends'])}",
             f"SUMMARY:{ics_escape(m['title'])}", f"STATUS:{status}"]
    if m["place"]:
        lines.append(f"LOCATION:{ics_escape(m['place'])}")
    if m["note"]:
        lines.append(f"DESCRIPTION:{ics_escape(m['note'])}")
    if m["organizer"]:
        lines.append(f"ORGANIZER:mailto:{m['organizer']}")
    for g in m["guests"]:
        lines.append(f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{g}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", str(text or "")).replace("\r", "")


def ics_time(params, value):
    """DTSTART/DTEND as local wall-clock time of this house."""
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return datetime.datetime.strptime(value, "%Y%m%d")
    m = re.fullmatch(r"(\d{8}T\d{4})(\d{2})?(Z?)", value)
    if not m:
        return None
    dt = datetime.datetime.strptime(m[1], "%Y%m%dT%H%M")
    if m[3]:
        return dt.replace(tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
    tzid = re.search(r"TZID=\"?([^;:\"]+)", params)
    if tzid:
        try:
            from zoneinfo import ZoneInfo
            return dt.replace(tzinfo=ZoneInfo(tzid[1])).astimezone().replace(tzinfo=None)
        except Exception:
            pass  # a zone name only Outlook knows: take the time as it is written
    return dt


def parse_ics(text):
    """The first VEVENT of an invitation, or None."""
    text = unfold(text)
    if "BEGIN:VEVENT" not in text:
        return None
    method = re.search(r"^METHOD:(\w+)", text, re.M)
    body = text.split("BEGIN:VEVENT", 1)[1].split("END:VEVENT", 1)[0]
    fields, guests = {}, []
    for line in body.split("\n"):
        if ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, _, params = head.partition(";")
        name = name.upper()
        if name == "ATTENDEE":
            guests.append(re.sub(r"^mailto:", "", value.strip(), flags=re.I))
        elif name not in fields:
            fields[name] = (params, value)
    if "DTSTART" not in fields:
        return None
    start = ics_time(*fields["DTSTART"])
    if not start:
        return None
    end = ics_time(*fields["DTEND"]) if "DTEND" in fields else None
    if not end or end <= start:
        end = start + (datetime.timedelta(days=1) if re.fullmatch(r"\d{8}", fields["DTSTART"][1].strip())
                       else datetime.timedelta(hours=1))
    get = lambda k: ics_unescape(fields[k][1].strip()) if k in fields else ""
    organizer = re.sub(r"^mailto:", "", get("ORGANIZER"), flags=re.I)
    status = get("STATUS").upper()
    return {
        "uid": get("UID"), "title": get("SUMMARY") or "(no title)", "starts": stamp(start), "ends": stamp(end),
        "place": get("LOCATION"), "note": get("DESCRIPTION"), "organizer": organizer, "guests": guests,
        "sequence": int(get("SEQUENCE") or 0) if get("SEQUENCE").isdigit() else 0,
        "method": (method[1].upper() if method else "REQUEST"),
        "cancelled": (method and method[1].upper() == "CANCEL") or status == "CANCELLED",
    }


def calendar_parts(mail):
    """Where an invitation can sit in a mail from the bridge: the text itself, or an attachment."""
    parts = [mail.get("text"), mail.get("body"), mail.get("ics")]
    for a in mail.get("attachments") or []:
        if isinstance(a, dict):
            kind = str(a.get("type") or a.get("contentType") or "").lower()
            name = str(a.get("name") or a.get("filename") or "").lower()
            if "calendar" in kind or name.endswith(".ics"):
                parts += [a.get("text"), a.get("content")]
    return [p for p in parts if isinstance(p, str) and "BEGIN:VCALENDAR" in p]


# --- invitation mails -----------------------------------------------------------------------------

def links(m):
    """Add-to-calendar links that work in any mail program, without an attachment."""
    s, e = utc(m["starts"]), utc(m["ends"])
    query = lambda d: urllib.parse.urlencode({k: v for k, v in d.items() if v})
    google = "https://calendar.google.com/calendar/render?" + query(
        {"action": "TEMPLATE", "text": m["title"], "dates": f"{s}/{e}", "details": m["note"], "location": m["place"]})
    iso = lambda t: parse_stamp(t).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    outlook = "https://outlook.live.com/calendar/0/deeplink/compose?" + query(
        {"subject": m["title"], "startdt": iso(m["starts"]), "enddt": iso(m["ends"]), "body": m["note"],
         "location": m["place"], "path": "/calendar/action/compose", "rru": "addevent"})
    return google, outlook


def invitation(m, kind="new"):
    """The mail that goes to the guests, as a draft: to, subject and text."""
    s = parse_stamp(m["starts"])
    date = f"{DAY_NAMES[s.weekday()]} {s.day} {MONTHS[s.month - 1]} {s.year}"
    end = parse_stamp(m["ends"])
    hours = f"{s:%H:%M} to {end:%H:%M}" if end.date() == s.date() else f"{s:%H:%M} to {end:%Y-%m-%d %H:%M}"
    prefix = {"new": "Invitation", "update": "Moved", "cancel": "Cancelled"}[kind]
    lead = {
        "new": "You are invited:",
        "update": "This meeting has moved. The new time:",
        "cancel": "This meeting is cancelled and does not take place:",
    }[kind]
    lines = [lead, "", m["title"], f"When: {date}, {hours}"]
    if m["place"]:
        lines.append(f"Where: {m['place']}")
    if m["guests"]:
        lines.append(f"Who: {', '.join(m['guests'])}")
    if m["note"]:
        lines += ["", m["note"]]
    if kind != "cancel":
        google, outlook = links(m)
        lines += ["", "Put it in your calendar:", f"Google: {google}", f"Outlook: {outlook}",
                  "", "Reply to this mail to say whether you can come."]
    return {"to": m["guests"], "subject": f"{prefix}: {m['title']} ({date} {s:%H:%M})",
            "text": "\n".join(lines), "ics": ics(m, "CANCEL" if kind == "cancel" else "REQUEST")}


def print_invitation(inv):
    print()
    print("The invitation, to make as a mail draft (the owner presses Send):")
    print(f"To: {', '.join(inv['to'])}")
    print(f"Subject: {inv['subject']}")
    print()
    print(inv["text"])


# --- commands -------------------------------------------------------------------------------------

def line(m):
    extra = f" at {m['place']}" if m["place"] else ""
    if m["source"] == "mail":
        guests = f", from {m['organizer']}" if m["organizer"] else ""
    else:
        guests = f", with {', '.join(m['guests'])}" if m["guests"] else ""
    s, e = parse_stamp(m["starts"]), parse_stamp(m["ends"])
    return f"  {s:%H:%M}-{e:%H:%M}  {m['title']}{extra}{guests}  [{m['id']}]"


def show_days(meetings, first, days):
    for i in range(days):
        day = first + datetime.timedelta(days=i)
        today = [m for m in meetings if parse_stamp(m["starts"]).date() <= day
                 <= (parse_stamp(m["ends"]) - datetime.timedelta(minutes=1)).date()]
        if today:
            print(f"{day_label(day)}:")
            for m in today:
                print(line(m))


def waiting_invites(con, mail):
    """Invitations in the inbox, newest first, each marked with what the calendar already knows."""
    out = []
    for x in mail:
        for part in calendar_parts(x)[:1]:
            ev = parse_ics(part)
            if not ev:
                continue
            row = con.execute("SELECT id, status, sequence FROM meetings WHERE uid = ?", (ev["uid"],)).fetchone() \
                if ev["uid"] else None
            state = "new"
            if row:
                state = "cancelled" if row["status"] == "cancelled" else (
                    "changed" if ev["sequence"] > row["sequence"] or ev["cancelled"] else "in calendar")
            out.append(dict(ev, mailId=str(x.get("id") or ""), sender=str(x.get("from") or ""),
                            subject=str(x.get("subject") or ""), state=state,
                            meetingId=row["id"] if row else None))
    return out


def cmd_overview(con, days=2):
    first = now().date()
    meetings = between(con, datetime.datetime.combine(first, datetime.time()),
                       datetime.datetime.combine(first + datetime.timedelta(days=days), datetime.time()))
    invites, note = [], ""
    try:
        invites = waiting_invites(con, bridge("/mail/inbox?n=50").get("mail", []))
    except Stop as e:
        note = str(e).replace("calendar: ", "")
    todo = [i for i in invites if i["state"] in ("new", "changed")]
    if AS_JSON:
        print(json.dumps({"today": str(first), "days": days, "meetings": meetings, "invites": invites,
                          "mailNote": note}))
        return
    if meetings:
        show_days(meetings, first, days)
    else:
        print("Nothing planned today or tomorrow." if days == 2 else f"Nothing planned in the next {days} days.")
    if todo:
        print(f"{len(todo)} invitation{'s' if len(todo) != 1 else ''} in the mailbox not in the calendar yet; "
              "`calendar invites` shows them.")
    elif note:
        print(f"(Invitations in the mail could not be read: {note}.)")


def cmd_week(con, args):
    words, _ = options(args, [])
    days = int(words[0]) if words and words[0].isdigit() else 7
    if not 1 <= days <= 366:
        fail("calendar: give a number of days between 1 and 366")
    first = now().date()
    meetings = between(con, now(), datetime.datetime.combine(first + datetime.timedelta(days=days), datetime.time()))
    if AS_JSON:
        print(json.dumps({"today": str(first), "days": days, "meetings": meetings}))
        return
    if not meetings:
        print(f"Nothing planned in the next {days} days.")
        return
    print(f"The next {days} days, {len(meetings)} meeting{'s' if len(meetings) != 1 else ''}:")
    show_days(meetings, first, days)


def cmd_search(con, args):
    words, _ = options(args, [])
    query = " ".join(words).strip().lower()
    if not query:
        fail("calendar: search for what? `calendar search dentist`")
    found = [m for m in between(con, now() - datetime.timedelta(days=30), now() + datetime.timedelta(days=365))
             if query in " ".join([m["title"], m["place"], m["note"], ",".join(m["guests"])]).lower()]
    if AS_JSON:
        print(json.dumps({"query": query, "meetings": found}))
        return
    if not found:
        print(f"Nothing with \"{query}\" in the calendar (the last 30 days and the next year).")
        return
    for m in found:
        print(f"{when_text(m)}  {m['title']}" + (f" at {m['place']}" if m["place"] else "") + f"  [{m['id']}]")


def show_one(m):
    print(f"{m['title']}  [{m['id']}]")
    print(f"When: {when_text(m)}")
    if m["place"]:
        print(f"Where: {m['place']}")
    if m["guests"]:
        print(f"Guests: {', '.join(m['guests'])}")
    if m["organizer"]:
        print(f"Organizer: {m['organizer']}")
    if m["note"]:
        print(f"Note: {m['note']}")
    if m["status"] == "cancelled":
        print("Cancelled.")
    if m["source"] == "mail":
        print(f"From an invitation in the mailbox (mail {m['mailId'][:8]}).")


def cmd_show(con, args):
    words, _ = options(args, [])
    if not words:
        fail("calendar: which meeting? `calendar show 3`")
    m = by_id(con, words[0])
    if AS_JSON:
        print(json.dumps({"meeting": m, "invitation": invitation(m) if m["guests"] else None}))
        return
    show_one(m)


def slot(words, opts, default_minutes):
    day, used = parse_date(words)
    if len(words) <= used:
        fail("calendar: at what time? like 14:30")
    start = datetime.datetime.combine(day, parse_time(words[used]))
    if start < now():
        fail(f"calendar: {start:%Y-%m-%d %H:%M} has already passed")
    return start, start + datetime.timedelta(minutes=minutes_of(opts.get("minutes"), default_minutes)), used + 1


def clashes(con, start, end, skip=None):
    return [m for m in between(con, start, end) if m["id"] != skip]


def report(m, kind, clash):
    inv = invitation(m, kind) if m["guests"] else None
    if AS_JSON:
        print(json.dumps({"meeting": m, "invitation": inv, "clashes": clash}))
        return
    verb = {"new": "Planned", "update": "Moved", "cancel": "Cancelled"}[kind]
    print(f"{verb}: {m['title']}, {when_text(m)}" + (f" at {m['place']}" if m["place"] else "") + f"  [{m['id']}]")
    for c in clash:
        print(f"Note: it overlaps with {c['title']} ({when_text(c)}).")
    if inv:
        print_invitation(inv)
    elif kind == "new":
        print("No guests, so there is no invitation to send.")


def cmd_meet(con, args):
    words, opts = options(args, ["minutes", "with", "where", "note"])
    if len(words) < 3:
        fail('calendar: calendar meet "<title>" <date> <time> [--minutes 60] [--with a@x.nl] [--where place]')
    title = words[0].strip()
    if not title:
        fail("calendar: the meeting needs a title")
    words = words[:1] + [w for x in words[1:] for w in x.split()]  # "next monday" may come as one word
    start, end, used = slot(words[1:], opts, 60)
    if len(words) > used + 1:
        fail(f"calendar: {' '.join(words[used + 1:])} is not understood; put the title in quotes")
    guests = check_addresses(split_addresses(opts.get("with")))
    clash = clashes(con, start, end)
    stamp_now = stamp(now())
    uid = f"{now():%Y%m%dT%H%M%S}-{os.urandom(6).hex()}@iris-calendar"
    cur = con.execute("INSERT INTO meetings (uid, title, starts, ends, place, note, guests, organizer, created) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (uid, title, stamp(start), stamp(end), opts.get("where", "").strip(),
                       opts.get("note", "").strip(), ", ".join(guests), house_address() if guests else "", stamp_now))
    con.commit()
    report(by_id(con, cur.lastrowid), "new", clash)


def cmd_move(con, args):
    words, opts = options(args, ["minutes"])
    if len(words) < 3:
        fail("calendar: calendar move <id> <date> <time> [--minutes N]")
    words = [w for x in words for w in x.split()]
    m = by_id(con, words[0])
    if m["status"] == "cancelled":
        fail(f"calendar: meeting {m['id']} is cancelled")
    if m["source"] == "mail":
        fail(f"calendar: {m['title']} is someone else's meeting; only {m['organizer'] or 'the organizer'} can move it")
    length = int((parse_stamp(m["ends"]) - parse_stamp(m["starts"])).total_seconds() // 60)
    start, end, _ = slot(words[1:], opts, length)
    con.execute("UPDATE meetings SET starts = ?, ends = ?, sequence = sequence + 1 WHERE id = ?",
                (stamp(start), stamp(end), m["id"]))
    con.commit()
    report(by_id(con, m["id"]), "update", clashes(con, start, end, skip=m["id"]))


def cmd_cancel(con, args):
    words, _ = options(args, [])
    if not words:
        fail("calendar: which meeting? `calendar cancel 3`")
    m = by_id(con, words[0])
    if m["status"] == "cancelled":
        fail(f"calendar: meeting {m['id']} is already cancelled")
    con.execute("UPDATE meetings SET status = 'cancelled', sequence = sequence + 1 WHERE id = ?", (m["id"],))
    con.commit()
    m = by_id(con, m["id"])
    if m["source"] == "mail":
        # Someone else's meeting: it leaves this calendar; telling the organizer is a reply to their mail.
        m = dict(m, guests=[])
        if not AS_JSON:
            print(f"Taken out of the calendar: {m['title']}, {when_text(m)}.")
            if m["organizer"]:
                print(f"To let {m['organizer']} know, reply to their invitation mail.")
            return
    report(m, "cancel", [])


def cmd_invitation(con, args):
    words, _ = options(args, [])
    if not words:
        fail("calendar: which meeting? `calendar invitation 3`")
    m = by_id(con, words[0])
    if not m["guests"]:
        fail(f"calendar: {m['title']} has no guests, so there is no invitation")
    if m["source"] == "mail":
        fail(f"calendar: {m['title']} is someone else's meeting; the invitation came from {m['organizer']}")
    kind = "cancel" if m["status"] == "cancelled" else ("update" if m["sequence"] else "new")
    inv = invitation(m, kind)
    if AS_JSON:
        print(json.dumps({"meeting": m, "invitation": inv}))
        return
    print_invitation(inv)


def cmd_ics(con, args):
    words, _ = options(args, [])
    if not words:
        fail("calendar: which meeting? `calendar ics 3`")
    m = by_id(con, words[0])
    sys.stdout.write(ics(m, "CANCEL" if m["status"] == "cancelled" else "REQUEST"))


def cmd_invites(con, args):
    invites = waiting_invites(con, bridge("/mail/inbox?n=200").get("mail", []))
    if AS_JSON:
        print(json.dumps({"invites": invites}))
        return
    if not invites:
        print("No invitations in the mailbox.")
        return
    print(f"Invitations in the mailbox ({len(invites)}):")
    for i, x in enumerate(invites, 1):
        what = "cancelled by the organizer" if x["cancelled"] else when_text(x)
        print(f"  [{i}] {x['title']}, {what}" + (f" at {x['place']}" if x["place"] else "")
              + f"  from {x['sender'] or x['organizer']}  ({x['state']})")
    if any(x["state"] in ("new", "changed") for x in invites):
        print("Put one in the calendar with: calendar accept <number>")


def cmd_accept(con, args):
    words, _ = options(args, [])
    if not words:
        fail("calendar: which invitation? `calendar accept 1` (see `calendar invites`)")
    invites = waiting_invites(con, bridge("/mail/inbox?n=200").get("mail", []))
    key = words[0]
    if key.isdigit() and 1 <= int(key) <= len(invites):
        hits = [invites[int(key) - 1]]
    else:
        hits = [x for x in invites if x["mailId"] and x["mailId"].startswith(key)]
    if not hits:
        fail(f"calendar: there is no invitation {key}; `calendar invites` shows them")
    if len(hits) > 1:
        fail(f"calendar: {key} fits more than one mail, give more characters")
    x = hits[0]
    uid = x["uid"] or f"mail-{x['mailId']}@iris-calendar"
    row = con.execute("SELECT * FROM meetings WHERE uid = ?", (uid,)).fetchone()
    if x["cancelled"]:
        if not row or row["status"] == "cancelled":
            print(f"{x['title']} is cancelled by the organizer and is not in the calendar.")
            return
        con.execute("UPDATE meetings SET status = 'cancelled', sequence = ? WHERE id = ?", (x["sequence"], row["id"]))
        con.commit()
        m = by_id(con, row["id"])
        if AS_JSON:
            print(json.dumps({"meeting": m, "done": "cancelled"}))
        else:
            print(f"Cancelled by the organizer, and taken out of the calendar: {m['title']}, {when_text(m)}.")
        return
    values = (x["title"], x["starts"], x["ends"], x["place"], x["note"], ", ".join(x["guests"]),
              x["organizer"] or x["sender"], x["mailId"], x["sequence"])
    if row:
        con.execute("UPDATE meetings SET title = ?, starts = ?, ends = ?, place = ?, note = ?, guests = ?, "
                    "organizer = ?, mail_id = ?, sequence = ?, status = 'confirmed' WHERE id = ?", values + (row["id"],))
        done, mid = "updated", row["id"]
    else:
        cur = con.execute("INSERT INTO meetings (title, starts, ends, place, note, guests, organizer, mail_id, "
                          "sequence, uid, source, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'mail', ?)",
                          values + (uid, stamp(now())))
        done, mid = "added", cur.lastrowid
    con.commit()
    m = by_id(con, mid)
    clash = clashes(con, parse_stamp(m["starts"]), parse_stamp(m["ends"]), skip=m["id"])
    if AS_JSON:
        print(json.dumps({"meeting": m, "done": done, "clashes": clash}))
        return
    print(f"{'In the calendar' if done == 'added' else 'Updated in the calendar'}: {m['title']}, {when_text(m)}"
          + (f" at {m['place']}" if m["place"] else "") + f"  [{m['id']}]")
    for c in clash:
        print(f"Note: it overlaps with {c['title']} ({when_text(c)}).")
    print(f"To say yes or no to {m['organizer'] or 'the organizer'}, reply to their mail.")


def main(argv):
    args = [a for a in argv if a != "--json"]
    if args and args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    commands = {
        "week": cmd_week, "search": cmd_search, "show": cmd_show, "meet": cmd_meet, "move": cmd_move,
        "cancel": cmd_cancel, "invitation": cmd_invitation, "ics": cmd_ics, "invites": cmd_invites,
        "accept": cmd_accept,
    }
    if args and args[0] not in commands:
        print(__doc__.strip())
        return 2
    con = db()
    try:
        if not args:
            cmd_overview(con)
        else:
            commands[args[0]](con, args[1:] + (["--json"] if AS_JSON else []))
    except Stop as e:
        if AS_JSON:
            print(json.dumps({"error": str(e).replace("calendar: ", "", 1)}))
            return 1
        print(str(e), file=sys.stderr)
        return 1
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
