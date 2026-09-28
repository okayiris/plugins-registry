#!/usr/bin/env python3
"""Let people book time with you on your house's address: appointment types with their own length, at a
place or by video call, and webinars with a number of seats. Kept in the plugin's own database.

For the owner:
  appointments                          today and what is coming, and the link of the booking page
  appointments type add "<name>" <minutes> place "<address>" [text "..."]
  appointments type add "<name>" <minutes> video [text "..."]
  appointments type add "<name>" <minutes> webinar seats <n> [text "..."]
  appointments types                    every type, with its link
  appointments type edit <n> <name|minutes|place|seats|text> <value>
  appointments type hide <n> / show <n> / remove <n>
  appointments webinar <type> <date> <time> [seats <n>]   a session of a webinar, like: webinar 3 2026-10-12 19:30
  appointments sessions                 the webinar sessions to come, with the seats taken
  appointments hours "<days> <from>-<to>, ..."             like: "mon-fri 09:00-17:00, sat 10:00-12:00"
  appointments block <date> [<from>-<to>] ["<why>"]        not available then (a whole day without times)
  appointments blocks / appointments unblock <n>
  appointments list [today|week|all]    the bookings
  appointments show <id>                one booking in full
  appointments cancel <id>              cancel a booking (the guest sees it on their page)
  appointments open / close             take bookings, or not
  appointments link
  appointments settings / appointments settings set <key> <value>

For the booking page (the route /book): the house runs this command with the request as JSON on stdin.
Actions: types, slots, book, view, cancel.

A video call gets your own meeting link when you set one (video_link), and otherwise its own room on
meet.jit.si, which needs no account. Times are in the house's own time zone.
"""
import json
import os
import re
import secrets
import select
import sqlite3
import sys
from datetime import date, datetime, time, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
ROUTE = "book"
DEFAULT = {"name": "", "open": "on", "hours": "mon-fri 09:00-17:00", "notice": "2", "days": "30",
           "step": "30", "buffer": "0", "video_link": "", "email": ""}
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
        "ma": 0, "di": 1, "wo": 2, "do": 3, "vr": 4, "za": 5, "zo": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
KINDS = {"place": "at a place", "video": "video call", "webinar": "webinar"}


# --- values and database --------------------------------------------------------------------------

def values():
    out = dict(DEFAULT)
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            kept = json.load(f)
        if isinstance(kept, dict):
            out.update({str(k): str(v) for k, v in kept.items()})
    except (OSError, ValueError):
        pass
    return out


def keep(key, value):
    data = {}
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data[key] = value
    with open(VALUES_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def number(key, low, high):
    try:
        return max(low, min(int(values()[key]), high))
    except ValueError:
        return int(DEFAULT[key])


def db():
    con = sqlite3.connect(DB_FILE, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    if not con.execute("select 1 from sqlite_master where type='table' and name='types'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def now():
    return datetime.now().astimezone().replace(microsecond=0)


def tz():
    return now().tzinfo


def iso(dt):
    return dt.isoformat(timespec="minutes")


def parse(value):
    d = datetime.fromisoformat(value)
    return d if d.tzinfo else d.replace(tzinfo=tz())


def at(day, hhmm):
    return datetime.combine(day, hhmm).astimezone()


def when(dt):
    d = dt.astimezone()
    days = (d.date() - now().date()).days
    label = {0: "today", 1: "tomorrow"}.get(days) or d.strftime("%a %d %b")
    return f"{label} {d.strftime('%H:%M')}"


# --- the week's hours -----------------------------------------------------------------------------

def parse_hours(text):
    """'mon-fri 09:00-17:00, sat 10:00-12:00' as {weekday: [(09:00, 17:00)], ...}."""
    out = {}
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        m = re.fullmatch(r"([a-z]+)(?:\s*-\s*([a-z]+))?\s+(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})", part.lower())
        if not m or m.group(1) not in DAYS or (m.group(2) and m.group(2) not in DAYS):
            raise ValueError(part)
        first, last = DAYS[m.group(1)], DAYS[m.group(2) or m.group(1)]
        start, end = time(int(m.group(3)), int(m.group(4))), time(int(m.group(5)), int(m.group(6)))
        if end <= start:
            raise ValueError(part)
        span = range(first, last + 1) if first <= last else list(range(first, 7)) + list(range(0, last + 1))
        for d in span:
            out.setdefault(d, []).append((start, end))
    return out


def hours():
    try:
        return parse_hours(values()["hours"])
    except ValueError:
        return parse_hours(DEFAULT["hours"])


def busy(con, start, end):
    """Is anything booked or blocked between two moments? The buffer keeps room around every booking."""
    pad = timedelta(minutes=number("buffer", 0, 240))
    for r in con.execute("select starts, ends from bookings where status = 'booked' and session_id is null "
                         "and ends > ? and starts < ?", (iso(start - pad - timedelta(days=1)), iso(end + pad + timedelta(days=1)))):
        if parse(r["starts"]) - pad < end and parse(r["ends"]) + pad > start:
            return True
    for r in con.execute("select s.starts, t.minutes from sessions s join types t on t.id = s.type_id "
                         "where s.cancelled = 0"):
        s = parse(r["starts"])
        if s - pad < end and s + timedelta(minutes=r["minutes"]) + pad > start:
            return True
    for r in con.execute("select starts, ends from blocks"):
        if parse(r["starts"]) < end and parse(r["ends"]) > start:
            return True
    return False


def free_slots(con, typ, first_day=None, days=None):
    """The moments a one-to-one type can still be booked, per day."""
    minutes = typ["minutes"]
    step = timedelta(minutes=number("step", 5, 240))
    earliest = now() + timedelta(hours=number("notice", 0, 24 * 14))
    horizon = days or number("days", 1, 180)
    start_day = first_day or now().date()
    week = hours()
    out = []
    for i in range(horizon):
        day = start_day + timedelta(days=i)
        slots = []
        for begin, end in week.get(day.weekday(), []):
            s, stop = at(day, begin), at(day, end)
            while s + timedelta(minutes=minutes) <= stop:
                e = s + timedelta(minutes=minutes)
                if s >= earliest and not busy(con, s, e):
                    slots.append(s.strftime("%H:%M"))
                s += step
        if slots:
            out.append({"day": day.isoformat(), "slots": slots})
    return out


def video_link(for_what):
    own = values()["video_link"].strip()
    if own:
        return own
    room = re.sub(r"[^a-z0-9]+", "-", (values()["name"] or "iris").lower()).strip("-")[:30] or "iris"
    return f"https://meet.jit.si/{room}-{for_what}-{secrets.token_hex(4)}"


# --- the booking page (route) ---------------------------------------------------------------------

def page_types(con):
    rows = con.execute("select * from types where visible = 1 order by position, id").fetchall()
    out = []
    for t in rows:
        item = {"id": t["id"], "name": t["name"], "minutes": t["minutes"], "kind": t["kind"], "text": t["text"],
                "place": t["place"] if t["kind"] == "place" else ""}
        if t["kind"] == "webinar":
            item["sessions"] = sessions_of(con, t)
        out.append(item)
    return out


def sessions_of(con, t):
    out = []
    for s in con.execute("select * from sessions where type_id = ? and cancelled = 0 and starts > ? order by starts",
                         (t["id"], iso(now()))):
        taken = con.execute("select count(*) from bookings where session_id = ? and status = 'booked'", (s["id"],)).fetchone()[0]
        out.append({"id": s["id"], "starts": s["starts"], "left": max(s["seats"] - taken, 0)})
    return out


def clean(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def book(body):
    if values()["open"] != "on":
        return {"error": "closed"}
    name, email, note = clean(body.get("name"), 80), clean(body.get("email"), 120), clean(body.get("note"), 500)
    if not name or not EMAIL.match(email):
        return {"error": "guest"}
    try:
        type_id = int(body.get("type"))
    except (TypeError, ValueError):
        return {"error": "type"}
    with db() as con:
        con.execute("begin immediate")        # checking and taking the moment is one step: never booked twice
        t = con.execute("select * from types where id = ? and visible = 1", (type_id,)).fetchone()
        if not t:
            return {"error": "type"}
        token = secrets.token_urlsafe(12)
        if t["kind"] == "webinar":
            try:
                sid = int(body.get("session"))
            except (TypeError, ValueError):
                return {"error": "session"}
            s = con.execute("select * from sessions where id = ? and type_id = ? and cancelled = 0", (sid, t["id"])).fetchone()
            if not s or parse(s["starts"]) <= now():
                return {"error": "session"}
            taken = con.execute("select count(*) from bookings where session_id = ? and status = 'booked'", (sid,)).fetchone()[0]
            if taken >= s["seats"]:
                return {"error": "full"}
            if con.execute("select 1 from bookings where session_id = ? and status = 'booked' and lower(email) = ?",
                           (sid, email.lower())).fetchone():
                return {"error": "twice"}
            start = parse(s["starts"])
            link = s["link"]
            session_id = sid
        else:
            try:
                day = date.fromisoformat(str(body.get("day")))
                hh, mm = map(int, str(body.get("time")).split(":"))
                start = at(day, time(hh, mm))
            except (TypeError, ValueError):
                return {"error": "slot"}
            end = start + timedelta(minutes=t["minutes"])
            # The moment must be one the page could have offered: in the hours, with notice, and free.
            offered = any(d["day"] == day.isoformat() and start.strftime("%H:%M") in d["slots"]
                          for d in free_slots(con, t, day, 1))
            if not offered:
                return {"error": "taken"}
            link = video_link("call") if t["kind"] == "video" else ""
            session_id = None
        end = start + timedelta(minutes=t["minutes"])
        cur = con.execute("insert into bookings (token, type_id, session_id, starts, ends, name, email, note, link, created) "
                          "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (token, t["id"], session_id, iso(start), iso(end),
                           name, email, note, link, iso(now())))
        bid = cur.lastrowid
    return {"booking": bid, "token": token, **view_of(bid)}


def view_of(bid):
    with db() as con:
        b = con.execute("select * from bookings where id = ?", (bid,)).fetchone()
        t = con.execute("select * from types where id = ?", (b["type_id"],)).fetchone()
    v = values()
    return {"booking": b["id"], "status": b["status"], "type": t["name"] if t else "", "kind": t["kind"] if t else "",
            "starts": b["starts"], "ends": b["ends"], "minutes": t["minutes"] if t else 0,
            "place": t["place"] if t and t["kind"] == "place" else "", "link": b["link"] if b["status"] == "booked" else "",
            "host": v["name"], "email": v["email"]}


def guest_booking(con, body):
    try:
        bid = int(body.get("booking"))
    except (TypeError, ValueError):
        return None
    b = con.execute("select * from bookings where id = ?", (bid,)).fetchone()
    # The id alone is not enough: without its own token a booking is not there for anyone.
    if not b or not secrets.compare_digest(b["token"], str(body.get("token") or "")):
        return None
    return b


def api(request):
    body = request.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = {}
    body = body if isinstance(body, dict) else {}
    query = request.get("query") or {}
    action = body.get("action") or query.get("action") or "types"
    v = values()
    if action == "types":
        with db() as con:
            return {"host": v["name"], "open": v["open"] == "on", "email": v["email"], "types": page_types(con)}
    if action == "slots":
        with db() as con:
            try:
                t = con.execute("select * from types where id = ? and visible = 1", (int(body.get("type")),)).fetchone()
            except (TypeError, ValueError):
                t = None
            if not t or t["kind"] == "webinar":
                return {"error": "type"}
            return {"type": t["id"], "days": free_slots(con, t)}
    if action == "book" and request.get("method", "POST") == "POST":
        return book(body)
    if action in ("view", "cancel"):
        with db() as con:
            b = guest_booking(con, body)
            if not b:
                return {"error": "unknown"}
            if action == "cancel" and request.get("method", "POST") == "POST":
                if b["status"] == "booked" and parse(b["starts"]) > now():
                    con.execute("update bookings set status = 'cancelled' where id = ?", (b["id"],))
        return view_of(b["id"])
    return {"error": "unknown action"}


# --- the owner ------------------------------------------------------------------------------------

def get_type(con, ref):
    ref = str(ref).strip()
    if ref.lstrip("#").isdigit():
        t = con.execute("select * from types where id = ?", (int(ref.lstrip("#")),)).fetchone()
        if not t:
            sys.exit(f"There is no appointment type #{ref.lstrip('#')}.")
        return t
    rows = con.execute("select * from types where lower(name) like ?", (f"%{ref.lower()}%",)).fetchall()
    if len(rows) == 1:
        return rows[0]
    sys.exit((f"Several types fit {ref}: " + ", ".join(f"#{r['id']} {r['name']}" for r in rows) + ".") if rows
             else f"There is no appointment type called {ref}.")


def type_line(t):
    what = KINDS[t["kind"]] + (f", {t['place']}" if t["kind"] == "place" and t["place"] else "") + (
        f", {t['seats']} seats" if t["kind"] == "webinar" else "")
    hidden = "  (hidden)" if not t["visible"] else ""
    return f"#{t['id']}  {t['name']}, {t['minutes']} min, {what}{hidden}"


def cmd_overview():
    v = values()
    with db() as con:
        types_ = con.execute("select count(*) from types where visible = 1").fetchone()[0]
        rows = con.execute("select b.*, t.name as tname, t.kind from bookings b join types t on t.id = b.type_id "
                           "where b.status = 'booked' and b.ends > ? order by b.starts limit 8", (iso(now()),)).fetchall()
    state = "open for bookings" if v["open"] == "on" else "closed for bookings"
    print(f"{v['name'] or 'Your booking page'} is {state}, with {types_} appointment type{'s' if types_ != 1 else ''}.")
    if not types_:
        print('Add the first with: appointments type add "Introduction" 30 video.')
    if rows:
        print("Coming up:")
        for b in rows:
            print(f"  {when(parse(b['starts']))}  {b['tname']} with {b['name']}")
    elif types_:
        print("Nothing booked yet.")
    missing = [label for key, label in (("name", "your name or your business's"), ("email", "a contact e-mail")) if not v[key]]
    if missing:
        print("Before you share the page, add " + " and ".join(missing) + " under Integrations.")


def cmd_type(args):
    if not args:
        sys.exit("appointments type add|edit|hide|show|remove ...")
    sub, rest = args[0], args[1:]
    if sub == "add":
        if len(rest) < 3:
            sys.exit('appointments type add "<name>" <minutes> <place "<address>"|video|webinar seats <n>> [text "..."]')
        name = rest[0].strip()
        if not rest[1].isdigit() or not 5 <= int(rest[1]) <= 600:
            sys.exit("The length is in minutes, from 5 to 600.")
        minutes, kind, extra = int(rest[1]), rest[2].lower(), rest[3:]
        if kind not in KINDS:
            sys.exit("An appointment is place, video or webinar.")
        place, seats, text_ = "", 1, ""
        i = 0
        if kind == "place":
            if not extra:
                sys.exit('Where? Like: place "Dorpsstraat 1, Utrecht".')
            place, i = extra[0], 1
        while i < len(extra):
            key = extra[i].lower()
            if key == "seats" and i + 1 < len(extra) and extra[i + 1].isdigit():
                seats, i = max(1, int(extra[i + 1])), i + 2
            elif key == "text" and i + 1 < len(extra):
                text_, i = extra[i + 1], i + 2
            else:
                sys.exit(f"I did not understand {extra[i]}. Use seats or text.")
        if kind == "webinar" and seats < 2:
            seats = 25
        with db() as con:
            pos = con.execute("select coalesce(max(position), 0) + 1 from types").fetchone()[0]
            cur = con.execute("insert into types (name, minutes, kind, place, seats, text, position, created) values (?, ?, ?, ?, ?, ?, ?, ?)",
                              (name[:80], minutes, kind, place[:200], seats, text_[:600], pos, iso(now())))
            t = con.execute("select * from types where id = ?", (cur.lastrowid,)).fetchone()
        print(f"New: {type_line(t)}.")
        if kind == "webinar":
            print(f"Add its sessions with: appointments webinar {t['id']} <date> <time>.")
        return
    if sub in ("hide", "show", "remove"):
        with db() as con:
            t = get_type(con, " ".join(rest))
            if sub == "remove":
                con.execute("delete from types where id = ?", (t["id"],))
                print(f"Forgot {t['name']}. Bookings already made stay.")
            else:
                con.execute("update types set visible = ? where id = ?", (1 if sub == "show" else 0, t["id"]))
                print(f"{t['name']} is {'on' if sub == 'show' else 'off'} the booking page.")
        return
    if sub == "edit":
        if len(rest) < 3:
            sys.exit("appointments type edit <n> <name|minutes|place|seats|text> <value>")
        field, value = rest[1].lower(), " ".join(rest[2:]).strip()
        with db() as con:
            t = get_type(con, rest[0])
            if field in ("minutes", "seats"):
                if not value.isdigit():
                    sys.exit(f"{field} is a number.")
                con.execute(f"update types set {field} = ? where id = ?", (int(value), t["id"]))
            elif field in ("name", "place", "text"):
                con.execute(f"update types set {field} = ? where id = ?", (value[:600], t["id"]))
            else:
                sys.exit("You can change name, minutes, place, seats or text.")
        print(f"{t['name']}: {field} is now {value}.")
        return
    sys.exit("appointments type add|edit|hide|show|remove ...")


def cmd_types():
    with db() as con:
        rows = con.execute("select * from types order by position, id").fetchall()
    if not rows:
        print('No appointment types yet. Add one with: appointments type add "Introduction" 30 video.')
        return
    print("Appointment types:")
    for t in rows:
        print(f"  {type_line(t)}")


def parse_day(text):
    t = text.strip().lower()
    today = now().date()
    if t in ("today", "vandaag"):
        return today
    if t in ("tomorrow", "morgen"):
        return today + timedelta(days=1)
    if t in DAYS:
        ahead = (DAYS[t] - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


def parse_time(text):
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", text.strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return time(int(m.group(1)), int(m.group(2)))


def cmd_webinar(args):
    if len(args) < 3:
        sys.exit("appointments webinar <type> <date> <time> [seats <n>]")
    day, hhmm = parse_day(args[1]), parse_time(args[2])
    if not day or not hhmm:
        sys.exit("A date is YYYY-MM-DD, today, tomorrow or a weekday; a time is like 19:30.")
    with db() as con:
        t = get_type(con, args[0])
        if t["kind"] != "webinar":
            sys.exit(f"{t['name']} is not a webinar.")
        seats = t["seats"]
        if len(args) >= 5 and args[3] == "seats" and args[4].isdigit():
            seats = int(args[4])
        start = at(day, hhmm)
        if start <= now():
            sys.exit("That moment has passed.")
        con.execute("insert into sessions (type_id, starts, seats, link) values (?, ?, ?, ?)",
                    (t["id"], iso(start), seats, video_link("webinar")))
    print(f"{t['name']} on {when(start)}, {seats} seats. It is on the booking page now.")


def cmd_sessions():
    with db() as con:
        rows = con.execute("select s.*, t.name from sessions s join types t on t.id = s.type_id "
                           "where s.cancelled = 0 and s.starts > ? order by s.starts", (iso(now()),)).fetchall()
        if not rows:
            print("No webinar sessions to come.")
            return
        print("Webinar sessions:")
        for s in rows:
            taken = con.execute("select count(*) from bookings where session_id = ? and status = 'booked'", (s["id"],)).fetchone()[0]
            print(f"  {when(parse(s['starts']))}  {s['name']}: {taken} of {s['seats']} seats taken, {s['link']}")


def cmd_hours(args):
    text = " ".join(args).strip()
    if not text:
        print(f"Your hours: {values()['hours']}.")
        return
    try:
        parse_hours(text)
    except ValueError as exc:
        sys.exit(f"I could not read {exc}. Write it like: mon-fri 09:00-17:00, sat 10:00-12:00.")
    keep("hours", text)
    print(f"Your hours are now: {text}.")


def cmd_block(args):
    if not args:
        sys.exit('appointments block <date> [<from>-<to>] ["<why>"]')
    day = parse_day(args[0])
    if not day:
        sys.exit("A date is YYYY-MM-DD, today, tomorrow or a weekday.")
    rest, span = args[1:], None
    if rest and re.fullmatch(r"\d{1,2}[:.]\d{2}-\d{1,2}[:.]\d{2}", rest[0]):
        a, b = rest[0].split("-")
        span, rest = (parse_time(a), parse_time(b)), rest[1:]
    start = at(day, span[0]) if span else at(day, time(0, 0))
    end = at(day, span[1]) if span else at(day + timedelta(days=1), time(0, 0))
    if end <= start:
        sys.exit("The end comes before the start.")
    note = " ".join(rest).strip()
    with db() as con:
        cur = con.execute("insert into blocks (starts, ends, note) values (?, ?, ?)", (iso(start), iso(end), note[:120]))
        clash = con.execute("select count(*) from bookings where status = 'booked' and starts < ? and ends > ?",
                            (iso(end), iso(start))).fetchone()[0]
    what = f"{day.strftime('%a %d %b')} " + (f"{span[0].strftime('%H:%M')} to {span[1].strftime('%H:%M')}" if span else "the whole day")
    print(f"Block #{cur.lastrowid}: not available {what}." + (f" Note: {clash} booking(s) already fall in it." if clash else ""))


def cmd_blocks(args, remove=False):
    with db() as con:
        if remove:
            if not args or not args[0].lstrip("#").isdigit():
                sys.exit("appointments unblock <n>")
            gone = con.execute("delete from blocks where id = ?", (int(args[0].lstrip("#")),)).rowcount
            print("Available again." if gone else "There is no such block.")
            return
        rows = con.execute("select * from blocks where ends > ? order by starts", (iso(now()),)).fetchall()
    if not rows:
        print("Nothing blocked.")
        return
    for r in rows:
        print(f"  #{r['id']}  {when(parse(r['starts']))} to {parse(r['ends']).strftime('%a %H:%M')}" + (f"  {r['note']}" if r["note"] else ""))


def cmd_list(args):
    which = args[0].lower() if args else "week"
    start = now()
    end = {"today": datetime.combine(start.date() + timedelta(days=1), time(0)).astimezone(),
           "week": start + timedelta(days=7), "all": start + timedelta(days=3650)}.get(which)
    if end is None:
        sys.exit("appointments list [today|week|all]")
    with db() as con:
        rows = con.execute("select b.*, t.name as tname, t.kind, t.place from bookings b join types t on t.id = b.type_id "
                           "where b.status = 'booked' and b.ends > ? and b.starts < ? order by b.starts",
                           (iso(start), iso(end))).fetchall()
    if not rows:
        print({"today": "Nothing booked for today.", "week": "Nothing booked in the coming week."}.get(which, "Nothing booked."))
        return
    for b in rows:
        where = b["place"] if b["kind"] == "place" else "video"
        print(f"  #{b['id']}  {when(parse(b['starts']))}  {b['tname']} with {b['name']} ({where})")


def cmd_show(args):
    if not args or not args[0].lstrip("#").isdigit():
        sys.exit("appointments show <id>")
    with db() as con:
        b = con.execute("select b.*, t.name as tname, t.kind, t.place from bookings b join types t on t.id = b.type_id "
                        "where b.id = ?", (int(args[0].lstrip("#")),)).fetchone()
    if not b:
        sys.exit(f"There is no booking #{args[0]}.")
    print(f"#{b['id']} {b['tname']}, {when(parse(b['starts']))} to {parse(b['ends']).strftime('%H:%M')}, {b['status']}.")
    print(f"{b['name']}, {b['email']}")
    if b["kind"] == "place":
        print(f"At {b['place']}.")
    elif b["link"]:
        print(f"Video: {b['link']}")
    if b["note"]:
        print(f"Note: {b['note']}")


def cmd_cancel(args):
    if not args or not args[0].lstrip("#").isdigit():
        sys.exit("appointments cancel <id>")
    with db() as con:
        b = con.execute("select * from bookings where id = ?", (int(args[0].lstrip("#")),)).fetchone()
        if not b:
            sys.exit(f"There is no booking #{args[0]}.")
        if b["status"] == "cancelled":
            sys.exit(f"Booking #{b['id']} was already cancelled.")
        con.execute("update bookings set status = 'cancelled' where id = ?", (b["id"],))
    print(f"Booking #{b['id']} of {b['name']} is cancelled; the moment is free again. Let {b['email']} know.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in DEFAULT:
        sys.exit("appointments settings set <" + "|".join(DEFAULT) + "> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "hours":
        return cmd_hours(args[2:])
    if key in ("notice", "days", "step", "buffer") and not value.isdigit():
        sys.exit(f"{key} is a whole number.")
    if key == "open" and value not in ("on", "off"):
        sys.exit("open is on or off.")
    if key == "email" and value and not EMAIL.match(value):
        sys.exit(f"{value} is not an e-mail address.")
    if key == "video_link" and value and not value.startswith("https://"):
        sys.exit("A video link starts with https://.")
    keep(key, value)
    print(f"{key}: {value or 'cleared'}.")


def read_request():
    if sys.stdin is None or sys.stdin.isatty():
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.5)
    except (OSError, ValueError):
        ready = [sys.stdin]
    if not ready:
        return None
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else None
    except ValueError:
        return None
    return data if isinstance(data, dict) and "route" in data else None


def main(argv):
    if not argv:
        request = read_request()
        if request is not None:
            print(json.dumps(api(request), ensure_ascii=False))
            return
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    commands = {
        "type": cmd_type, "types": lambda a: cmd_types(), "webinar": cmd_webinar, "sessions": lambda a: cmd_sessions(),
        "hours": cmd_hours, "block": cmd_block, "blocks": lambda a: cmd_blocks(a), "unblock": lambda a: cmd_blocks(a, True),
        "list": cmd_list, "show": cmd_show, "cancel": cmd_cancel, "settings": cmd_settings,
        "open": lambda a: (keep("open", "on"), print("The booking page takes bookings.")),
        "close": lambda a: (keep("open", "off"), print("The booking page is closed: it shows the types but takes no bookings.")),
        "link": lambda a: print(f"The booking page is at https://{os.environ.get('IRIS_HOUSE', '<your house>')}.okayiris.com/{ROUTE}."),
    }
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd in commands:
        commands[cmd](rest)
    else:
        sys.exit("appointments type add, appointments list, appointments hours. `appointments help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
