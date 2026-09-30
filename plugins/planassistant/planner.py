#!/usr/bin/env python3
"""The plan assistant: your day from morning to evening, with the family and the road in it.

It keeps what no other plugin keeps (promises, prep, reviews, who brings and picks up the children, the
evening triage) and reads the rest from the plugins this house already has, when they are switched on:

  appointments   calendar (this house's own), calendars (.ics links), google (Google Calendar)
  travel time    maps (Google, with traffic, from anywhere) or travel (OSRM or TomTom, from home)
  parking, food  maps
  tasks          todoist, next to the planner's own

Morning
  planner                                   today: promises first, the timeline with meals and breaks,
                                            when to leave, what to prepare, clashes and open questions
  planner day <day>                         the same for another day (tomorrow, friday, 2026-10-02)
  planner next                              what is on now, and the next appointment
  planner sources                           which plugins it reads, and what is missing

On the road
  planner leave [<appointment>] [--soon]    when to leave; --soon only answers when it is almost time
  planner near <appointment|address>        parking, a quick bite and a place to sit down (through maps)

The family
  planner person <name> [kid|partner|family|team]    planner person remove <name>    planner people
  planner owner <calendar|word> <who> [--bring <who>] [--pick <who>]
                                            whose calendar or kind of appointment it is, and who drives:
                                            asked once, then remembered
  planner owners                            planner owner remove <calendar|word>

Before and after a meeting
  planner prep <appointment> ["<what to finish first>"]
  planner review <appointment> [--feeling <word>] [--outcome "<text>"] [--action "<text>"]...
  planner reviews                           the appointments still waiting for "how was it?"
  planner evaluate on|off <word>            ask afterwards about appointments with this word

Tasks and the evening
  planner task "<title>" [<day>] [--before <appointment>]
  planner promise "<title>" [<day>]         something you promised; tomorrow by default, on top then
  planner done <#id|title>    planner undo <#id>    planner drop <#id>    planner tasks [<day>|later]
  planner move <#id>[,<#id>] <tomorrow|overmorrow|nextweek|later|<day>>
  planner recap                             what you did today, and what is still open
  planner tomorrow                          a look ahead, ready for the morning

  planner settings                          planner settings set <key> <value>

An appointment is its reference (c3, f1c9 from the day's list) or a word of its title. A day is today,
tomorrow, overmorrow, a weekday, nextweek, later, 2026-10-02 or 2-10. Add --json for the window.
New appointments go in the calendar itself (calendar meet, or the Google or Outlook calendar).
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time as clock
from datetime import date, datetime, time, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
FIELDS_FILE = os.path.join(HERE, "settings.json")
DEFAULT = {"transport": "car", "buffer": "10", "warn": "15", "day_start": "08:00", "day_end": "18:00",
           "breakfast": "", "lunch": "12:30", "dinner": "18:00", "break_after": "120", "break_minutes": "15"}
MEALS = (("breakfast", "Breakfast", 20), ("lunch", "Lunch", 30), ("dinner", "Dinner", 45))
ROLES = ("kid", "partner", "family", "team")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_WORDS = {**{d: i for i, d in enumerate(WEEKDAYS)}, **{d[:3]: i for i, d in enumerate(WEEKDAYS)},
                 **{d: i for i, d in enumerate(["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
                                                "zaterdag", "zondag"])}}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
MAPS_MODE = {"car": "driving", "bike": "bicycling", "walk": "walking", "transit": "transit"}
JSON = False


class Stop(Exception):
    pass


def fail(message):
    raise Stop(message)


def emit(data, lines):
    if JSON:
        print(json.dumps(data, ensure_ascii=False, default=str))
    else:
        print("\n".join(line for line in lines if line is not None).rstrip())


# --- settings (the form under Integrations reads and writes the same file) --------------------------------------

def fields():
    try:
        with open(FIELDS_FILE, encoding="utf-8") as f:
            return [x for x in json.load(f).get("fields", []) if isinstance(x, dict) and x.get("key")]
    except (OSError, ValueError):
        return []


def values():
    out = {}
    for f in fields():
        out[f["key"]] = str(f["options"][0]) if f.get("type") == "choice" and f.get("options") else ""
    out.update(DEFAULT)
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            kept = json.load(f)
        if isinstance(kept, dict):
            out.update({str(k): str(v) for k, v in kept.items()})
    except (OSError, ValueError):
        pass
    return out


def keep(key, value):
    kept = {}
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            kept = loaded
    except (OSError, ValueError):
        pass
    kept[key] = value
    tmp = VALUES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kept, f, indent=2, ensure_ascii=False)
    os.replace(tmp, VALUES_FILE)


def number(settings, key):
    try:
        return max(0, int(float(settings.get(key) or DEFAULT.get(key, "0"))))
    except ValueError:
        return int(DEFAULT.get(key, "0"))


def listed(settings, key):
    return [x.strip() for x in str(settings.get(key, "")).split(",") if x.strip()]


def settings_command(args):
    if not args:
        print(json.dumps(values(), indent=2, ensure_ascii=False))
        return
    if args[0] != "set" or len(args) < 2:
        fail("planner settings set <key> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    known = {f["key"]: f for f in fields()}
    if key not in known:
        fail(f"There is no setting {key}. There are: {', '.join(known)}.")
    kind = known[key].get("type")
    if kind == "number" and value and not re.fullmatch(r"\d{1,4}", value):
        fail(f"{known[key]['label']} is a number of minutes, like 15.")
    if kind == "choice" and value not in known[key].get("options", []):
        fail(f"{known[key]['label']} is one of {', '.join(known[key]['options'])}.")
    if key in ("day_start", "day_end", "breakfast", "lunch", "dinner") and value:
        at = parse_time(value)
        if not at:
            fail(f"{known[key]['label']} is a time like 12:30, or empty.")
        value = at.strftime("%H:%M")
    keep(key, value)
    print(f"{known[key]['label']}: {value or 'empty'}.")


# --- the database --------------------------------------------------------------------------------------------

def connect():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    if not con.execute("select 1 from sqlite_master where type='table' and name='tasks'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def meta(con, key, value=None):
    if value is None:
        row = con.execute("select value from meta where key = ?", (key,)).fetchone()
        return row["value"] if row else ""
    con.execute("insert into meta (key, value) values (?, ?) on conflict(key) do update set value = excluded.value",
                (key, value))
    con.commit()
    return value


def stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# --- days and times ------------------------------------------------------------------------------------------

def parse_time(word):
    found = re.fullmatch(r"(\d{1,2})(?:[:.h](\d{2}))?", str(word).strip().lower())
    if not found:
        return None
    hour, minute = int(found.group(1)), int(found.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def parse_day(word, today=None, later_ok=False):
    """A date, 'later', or None. A weekday is the next one after today."""
    today = today or date.today()
    w = str(word).strip().lower().replace(" ", "")
    if w in ("today", "vandaag", "now"):
        return today
    if w in ("tomorrow", "morgen"):
        return today + timedelta(days=1)
    if w in ("overmorrow", "dayaftertomorrow", "overmorgen"):
        return today + timedelta(days=2)
    if w in ("nextweek", "volgendeweek"):
        return today + timedelta(days=7 - today.weekday())
    if w in ("later", "someday", "ooit") and later_ok:
        return "later"
    w = w.removeprefix("next")
    if w in WEEKDAY_WORDS:
        ahead = (WEEKDAY_WORDS[w] - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    try:
        return date.fromisoformat(w)
    except ValueError:
        pass
    found = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})(?:[-/](\d{4}))?", w)
    if found:
        try:
            d = date(int(found.group(3) or today.year), int(found.group(2)), int(found.group(1)))
        except ValueError:
            return None
        if not found.group(3) and d < today:
            d = d.replace(year=d.year + 1)
        return d
    return None


def join_days(words):
    """'next week' and 'volgende week' as one word."""
    out = []
    for w in words:
        if out and w.lower() == "week" and out[-1].lower() in ("next", "volgende"):
            out[-1] = "nextweek"
        else:
            out.append(w)
    return out


def hm(dt):
    return dt.strftime("%H:%M")


def day_name(d, today=None):
    today = today or date.today()
    if d == today:
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} {MONTHS[d.month - 1]}"


def long_day(d):
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} {MONTHS[d.month - 1]}"


def minutes_text(minutes):
    minutes = max(1, round(minutes))
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h" + (f" {rest} min" if rest else "")


def options(args, flags, multi=()):
    """Split --flag value pairs out of the words. Flags in `flags` take a value; others are switches."""
    rest, found = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--") and a[2:] in flags:
            if i + 1 >= len(args):
                fail(f"{a} needs a value.")
            if a[2:] in multi:
                found.setdefault(a[2:], []).append(args[i + 1])
            else:
                found[a[2:]] = args[i + 1]
            i += 2
        elif a.startswith("--") and len(a) > 2:
            found[a[2:]] = True
            i += 1
        else:
            rest.append(a)
            i += 1
    return rest, found


# --- people and who an appointment belongs to ----------------------------------------------------------------

def people(con):
    return con.execute("select * from people order by role = 'kid' desc, name").fetchall()


def person(con, name, allow=("me", "family")):
    """'me', 'family' or a known name, from what was said."""
    n = str(name or "").strip()
    low = n.lower()
    if low in ("me", "i", "myself", "ik", "mij", "zelf") and "me" in allow:
        return "me"
    if low in ("family", "everyone", "all", "gezin", "iedereen") and "family" in allow:
        return "family"
    rows = people(con)
    for r in rows:
        if r["name"].lower() == low:
            return r["name"]
    close = [r for r in rows if r["name"].lower().startswith(low)] if low else []
    if len(close) == 1:
        return close[0]["name"]
    names = ", ".join(r["name"] for r in rows) or "nobody yet"
    fail(f"I do not know {n or 'that person'}. Known: {names}. Add them with: planner person {n or '<name>'} kid.")


def rules(con):
    return {r["pattern"]: dict(r) for r in con.execute("select * from rules")}


def rule_for(title, calendar, found, names):
    """The remembered rule for an appointment: a word of its title first, then its calendar."""
    t = title.lower()
    for pattern in sorted((p for p in found if not p.startswith("calendar:")), key=len, reverse=True):
        if pattern in t:
            return found[pattern]
    by_calendar = found.get("calendar:" + calendar.lower()) if calendar else None
    for name in names:
        if re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", t):
            return dict(by_calendar or {}, who=name)
    return by_calendar


# --- the other plugins of this house ---------------------------------------------------------------------------

def sibling(name, args, timeout=90):
    """Run another plugin's command with --json. None when it is not in this house (or switched off)."""
    exe = shutil.which(name)
    if not exe:
        return None
    try:
        p = subprocess.run([exe] + args + ["--json"], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"{name} did not answer in time"}
    except (OSError, subprocess.SubprocessError) as problem:
        return {"error": f"{name} did not run ({problem})"}
    out = (p.stdout or "").strip()
    try:
        data = json.loads(out.splitlines()[-1] if out else "")
    except ValueError:
        return {"error": (out or p.stderr or f"{name} gave no answer").strip().splitlines()[-1][:200]}
    return data if isinstance(data, dict) else {"error": f"{name} gave no answer"}


def local(stamp_text):
    """A time from another plugin as the house's own time, without a zone."""
    text = str(stamp_text or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.combine(date.fromisoformat(text), time(0, 0)), True
    at = datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T"))
    if at.tzinfo:
        at = at.astimezone().replace(tzinfo=None)
    return at, False


def appointment(title, start, end, place, source, calendar, ref, allday=False):
    return {"ref": ref, "title": title or "(no title)", "start": start, "end": end, "place": place or "",
            "source": source, "calendar": calendar, "allday": allday, "who": "", "bring": "", "pick": "",
            "evaluate": False}


def from_calendar(first_day, last_day, notes):
    today = date.today()
    if first_day >= today and last_day <= today + timedelta(days=1):
        data = sibling("calendar", [])
    else:
        data = sibling("calendar", ["week", str(max(1, (last_day - today).days + 1))])
    if data is None:
        return []
    if data.get("error"):
        notes.append(f"The calendar could not be read: {data['error']}.")
        return []
    out = []
    for m in data.get("meetings") or []:
        if m.get("status") == "cancelled":
            continue
        start, _ = local(m["starts"])
        end, _ = local(m["ends"])
        out.append(appointment(m.get("title"), start, end, m.get("place"), "calendar", "calendar", f"c{m['id']}"))
    return out


def from_calendars(first_day, last_day, notes):
    today = date.today()
    data = sibling("calendars", ["week", str(max(1, (last_day - today).days + 1))])
    if data is None:
        return []
    if data.get("error"):
        notes.append(f"Your calendars could not be read: {data['error']}.")
        return []
    notes += [f"One calendar: {c}." for c in data.get("complaints") or []]
    out = []
    for e in data.get("events") or []:
        start, _ = local(e["start"])
        end, _ = local(e["end"])
        out.append(appointment(e.get("title"), start, end, e.get("place"), "calendars", e.get("calendar") or "",
                               "", bool(e.get("allday"))))
    return out


def from_google(first_day, last_day, notes):
    today = date.today()
    exe = shutil.which("google")
    if not exe:
        return []
    try:
        p = subprocess.run([exe, "cal", "list", str(max(1, (last_day - today).days + 1))],
                           capture_output=True, text=True, timeout=90)
        data = json.loads(p.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        notes.append("Google Calendar could not be read; is Google linked under Integrations?")
        return []
    out = []
    for e in data.get("events") or []:
        try:
            start, allday = local(e.get("start"))
            end, _ = local(e.get("end") or e.get("start"))
        except ValueError:
            continue
        out.append(appointment(e.get("title"), start, end, e.get("where"), "google", "Google", "", allday))
    return out


def sources():
    return {name: bool(shutil.which(name)) for name in ("calendar", "calendars", "google", "maps", "travel", "todoist")}


def key_of(entry):
    return f"{entry['start']:%Y-%m-%d %H:%M}|{entry['title']}"


def entries_between(con, settings, first_day, last_day, notes=None):
    """Every appointment from first_day to last_day in the house's calendars, with who it is for."""
    notes = notes if notes is not None else []
    found = from_calendar(first_day, last_day, notes) + from_calendars(first_day, last_day, notes) + \
        from_google(first_day, last_day, notes)
    known = rules(con)
    family = people(con)
    names = [p["name"] for p in family]
    words = [w.lower() for w in listed(settings, "evaluate")]
    for e in found:
        if not e["ref"]:
            e["ref"] = {"calendars": "f", "google": "g"}[e["source"]] + hashlib.sha1(key_of(e).encode()).hexdigest()[:4]
        rule = rule_for(e["title"], e["calendar"], known, names)
        if rule:
            e.update(who=rule.get("who") or "", bring=rule.get("bring") or "", pick=rule.get("pick") or "")
        elif e["source"] != "calendars" or not family:
            e["who"] = "me"   # the house's own calendar and Google are the owner's
        e["evaluate"] = any(w in e["title"].lower() for w in words)
    seen = {}
    order = {"calendar": 0, "google": 1, "calendars": 2}
    for e in sorted(found, key=lambda x: (x["start"], order[x["source"]], x["title"].lower())):
        same = seen.get((e["start"], e["title"].lower()))
        if same:   # one appointment in two calendars
            same.setdefault("also", []).append(e["calendar"])
            continue
        seen[(e["start"], e["title"].lower())] = e
    lo, hi = datetime.combine(first_day, time(0, 0)), datetime.combine(last_day + timedelta(days=1), time(0, 0))
    return [e for e in seen.values() if e["end"] > lo and e["start"] < hi]


# --- travel time, through maps or travel -----------------------------------------------------------------------

def travel_time(con, settings, origin, place, arrive):
    """{minutes, traffic, via, from} from origin (an address, or None for home) to place, or {error}."""
    mode = settings.get("transport") or "car"
    key = f"{origin or 'home'}>{place}|{mode}|{arrive:%Y-%m-%d %H}"
    row = con.execute("select * from routes where key = ?", (key,)).fetchone()
    if row and clock.time() - row["at"] < 20 * 60:
        return json.loads(row["answer"])
    answer = None
    if shutil.which("maps"):
        args = ["route"] + ([origin] if origin else []) + [place, "--mode", MAPS_MODE.get(mode, "driving")]
        data = sibling("maps", args)
        if data and not data.get("error") and data.get("seconds"):
            seconds = data.get("traffic_seconds") or data["seconds"]
            answer = {"minutes": round(seconds / 60), "traffic": bool(data.get("traffic_seconds")), "via": "maps",
                      "from": "your previous appointment" if origin else "home"}
    if answer is None and shutil.which("travel"):
        data = sibling("travel", ["naar", place, "--om", arrive.strftime("%H:%M")])
        if data and not data.get("error") and data.get("seconds"):
            seconds = data["seconds"]
            if mode == "bike":
                seconds = data["meters"] / 1000 / 15 * 3600
            elif mode == "walk":
                seconds = data["meters"] / 1000 / 5 * 3600
            answer = {"minutes": round(seconds / 60), "traffic": bool(data.get("traffic")), "via": "travel",
                      "from": "home"}
        elif data and data.get("error"):
            return {"error": data["error"]}
    if answer is None:
        if not (shutil.which("maps") or shutil.which("travel")):
            return {"error": "For travel times I use the travel plugin (free) or maps (Google, with traffic). "
                             "Install one of them and set your home address there."}
        return {"error": f"No route to {place}."}
    con.execute("insert or replace into routes (key, answer, at) values (?, ?, ?)",
                (key, json.dumps(answer), clock.time()))
    con.commit()
    return answer


def mine(e):
    return e["who"] in ("me", "family", "")


def rides(con, settings, entries):
    """Bringing and picking up, for the appointments someone is driven to."""
    out = []
    for e in entries:
        if e["allday"] or not (e["bring"] or e["pick"]):
            continue
        minutes = 15
        if e["place"]:
            t = travel_time(con, settings, None, e["place"], e["start"])
            minutes = max(5, t.get("minutes") or 15)
        for kind, driver in (("bring", e["bring"]), ("pick", e["pick"])):
            if not driver:
                continue
            at = e["start"] if kind == "bring" else e["end"]
            if e["who"] in ("me", "family", ""):
                what = f"{kind.capitalize()} for {e['title']}"
            elif kind == "bring":
                what = f"Bring {e['who']} to {e['title']}"
            else:
                what = f"Pick up {e['who']} from {e['title']}"
            out.append({"ref": "", "title": what, "start": at - timedelta(minutes=minutes),
                        "end": at + timedelta(minutes=minutes), "at": at, "place": e["place"], "who": driver,
                        "ride": kind, "for": e["ref"], "source": "ride", "calendar": "", "allday": False,
                        "evaluate": False, "bring": "", "pick": ""})
    return out


def busy_of(entries, who="me"):
    spans = []
    for e in entries:
        if e["allday"]:
            continue
        if (who == "me" and mine(e)) or e["who"] == who or (e["who"] == "family" and who != "me"):
            spans.append((e["start"], e["end"], e))
    return sorted(spans, key=lambda s: s[0])


def clashes(con, entries):
    """Two things at once for one person: yourself, a child with two activities, or one driver twice."""
    persons = ["me"] + [p["name"] for p in people(con)]
    found, seen = [], set()
    for who in persons:
        spans = busy_of(entries, who)
        for i, (s1, e1, a) in enumerate(spans):
            for s2, e2, b in spans[i + 1:]:
                if s2 >= e1:
                    break
                if b.get("for") == a["ref"] or a.get("for") == b["ref"]:
                    continue   # a ride and the appointment it is for
                pair = tuple(sorted((key_of(a), key_of(b))))
                if pair in seen:
                    continue
                seen.add(pair)
                found.append({"who": who, "a": a, "b": b, "from": max(s1, s2), "until": min(e1, e2)})
    return found


def free_at(spans, start, end):
    return all(not (s < end and start < e) for s, e in spans)


def blocks(settings, day, entries):
    """Meals and breaks, placed where the day has room. (blocks, warnings)."""
    spans = [(s, e) for s, e, _ in busy_of(entries, "me")]
    out, warnings = [], []
    for key, label, length in MEALS:
        at = parse_time(settings.get(key, ""))
        if not at:
            continue
        wanted = datetime.combine(day, at)
        span = timedelta(minutes=length)
        tries = [wanted] + [wanted + timedelta(minutes=sign * step) for step in range(15, 91, 15) for sign in (1, -1)]
        spot = next((t for t in tries if free_at(spans, t, t + span)), None)
        if spot:
            out.append({"title": label, "start": spot, "end": spot + span, "kind": "meal"})
            spans.append((spot, spot + span))
        else:
            warnings.append(f"No room for {label.lower()} around {hm(wanted)}.")
    after = timedelta(minutes=number(settings, "break_after") or 120)
    pause = timedelta(minutes=number(settings, "break_minutes") or 15)
    work = sorted((s, e) for s, e, _ in busy_of(entries, "me"))
    stretches = []
    for s, e in work:
        if stretches and s <= stretches[-1][1] + timedelta(minutes=5):
            stretches[-1][1] = max(stretches[-1][1], e)
        else:
            stretches.append([s, e])
    taken = sorted(spans)
    for s, e in stretches:
        if e - s < after:
            continue
        if free_at(taken, e, e + pause):
            out.append({"title": "Break", "start": e, "end": e + pause, "kind": "break"})
            taken.append((e, e + pause))
        else:
            warnings.append(f"Busy from {hm(s)} to {hm(e)} without a break.")
    return sorted(out, key=lambda b: b["start"]), warnings


def departures(con, settings, day, entries):
    """For your own appointments with an address: when to leave, and from where."""
    out = []
    if not (shutil.which("maps") or shutil.which("travel")):
        return out
    buffer = number(settings, "buffer")
    extra = 5 if (settings.get("transport") or "car") == "car" else 0
    last_place, last_end = None, None
    for e in sorted((x for x in entries if not x["allday"] and x["start"].date() == day and mine(x)),
                    key=lambda x: x["start"]):
        if not e["place"]:
            continue
        arrive = e.get("at") or e["start"]
        origin = last_place if last_end and arrive - last_end < timedelta(hours=3) else None
        if origin != e["place"]:
            t = travel_time(con, settings, origin, e["place"], arrive)
            if not t.get("error"):
                travel = t["minutes"] + extra
                out.append({"for": e["ref"] or e["title"], "title": e["title"], "arrive": arrive,
                            "leave": arrive - timedelta(minutes=travel + buffer), "minutes": travel,
                            "traffic": t["traffic"], "place": e["place"], "from": t["from"]})
        last_place, last_end = e["place"], (e["at"] if e["source"] == "ride" else e["end"])
    return out


def resolve(con, settings, word, days=7, back=1):
    """An appointment from its reference or a word of its title, today first."""
    today = date.today()
    entries = entries_between(con, settings, today - timedelta(days=back), today + timedelta(days=days))
    w = str(word).strip().lower()
    for e in entries:
        if e["ref"].lower() == w:
            return e, entries
    hits = [e for e in entries if w and w in e["title"].lower()]
    if not hits:
        fail(f"No appointment {word} between yesterday and {days} days ahead.")
    now = datetime.now()
    hits.sort(key=lambda e: (e["end"] < now, abs((e["start"] - now).total_seconds())))
    return hits[0], entries


# --- tasks -----------------------------------------------------------------------------------------------------

def task_row(con, word):
    w = str(word).strip().lstrip("#")
    if w.isdigit():
        row = con.execute("select * from tasks where id = ?", (int(w),)).fetchone()
        if not row:
            fail(f"There is no task #{w}.")
        return row
    rows = con.execute("select * from tasks where done = '' and title like ? order by day, id",
                       (f"%{w}%",)).fetchall()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        fail(f"No open task with {word}.")
    fail(f"More than one open task has {word}: " + ", ".join(f"#{r['id']} {r['title']}" for r in rows[:5]) + ".")


def task_json(r):
    return {"id": r["id"], "title": r["title"], "day": r["day"], "promised": bool(r["promised"]),
            "before": r["before"], "done": r["done"], "moved": r["moved"]}


def open_tasks(con, day):
    """Tasks for a day, and the ones left behind before it (they did not go away)."""
    return con.execute("select * from tasks where done = '' and day != 'later' and day <= ? "
                       "order by promised desc, day, id", (day.isoformat(),)).fetchall()


def task_line(r, today):
    bits = [f"#{r['id']} {r['title']}"]
    if r["promised"]:
        bits.append("(promised)")
    if r["day"] not in ("later", today.isoformat()) and r["day"] < today.isoformat():
        bits.append(f"(since {day_name(date.fromisoformat(r['day']), today)})")
    return " ".join(bits)


# --- the day's picture, as text and as JSON --------------------------------------------------------------------

def entry_json(e):
    return {"ref": e["ref"], "title": e["title"], "start": e["start"].strftime("%Y-%m-%d %H:%M"),
            "end": e["end"].strftime("%Y-%m-%d %H:%M"), "place": e["place"], "who": e["who"] or "?",
            "source": e["source"], "calendar": e["calendar"], "allday": e["allday"], "evaluate": e["evaluate"],
            "ride": e.get("ride", ""), "at": e["at"].strftime("%H:%M") if e.get("at") else "",
            "also": e.get("also", []), "key": key_of(e)}


def picture(con, settings, day):
    today = date.today()
    now = datetime.now()
    notes = []
    both = entries_between(con, settings, day, day + timedelta(days=1), notes)
    lo, hi = datetime.combine(day, time(0, 0)), datetime.combine(day + timedelta(days=1), time(0, 0))
    entries = [e for e in both if e["end"] > lo and e["start"] < hi]
    entries += rides(con, settings, entries)
    entries.sort(key=lambda e: e["start"])
    meals, warnings = blocks(settings, day, entries)
    leaves = departures(con, settings, day, entries)
    found = clashes(con, entries)
    tasks = open_tasks(con, day) if day <= today else con.execute(
        "select * from tasks where done = '' and day = ? order by promised desc, id", (day.isoformat(),)).fetchall()
    done_today = con.execute("select * from tasks where done like ? order by done",
                             (f"{day.isoformat()}%",)).fetchall()
    keys = {key_of(e): e for e in entries}
    prep = {}
    for r in con.execute("select * from tasks where before != '' and done = ''"):
        if r["before"] in keys:
            prep.setdefault(r["before"], []).append(r)
    questions = []
    if people(con):
        unknown = {}
        for e in both:
            if e["source"] == "calendars" and not e["who"]:
                unknown.setdefault(e["calendar"] or "(no name)", e)
        for feed, e in unknown.items():
            questions.append({"calendar": feed, "example": e["title"],
                              "ask": f"Whose calendar is {feed} (like {e['title']} at {hm(e['start'])})? "
                                     f"Say: planner owner \"{feed}\" <name|me|family>. Asked once, then remembered."})
    reviewed = {r["key"] for r in con.execute("select key from reviews")}
    to_review = [e for e in entries if e["evaluate"] and e["end"] <= now and key_of(e) not in reviewed]
    mine_now = [e for e in entries if not e["allday"] and (mine(e) or e["who"] == "me")]
    current = next((e for e in mine_now if e["start"] <= now < e["end"]), None) if day == today else None
    upcoming = next((e for e in mine_now if e["start"] > now), None) if day >= today else None
    promised_by = meta(con, "looked_ahead")
    todoist = []
    if day == today:
        data = sibling("todoist", [])
        if data and data.get("error"):
            notes.append(f"Todoist could not be read: {data['error']}")
        elif data:
            todoist = data.get("tasks") or []
    return {"todoist": todoist, "entries": entries, "blocks": meals, "warnings": warnings + notes, "leaves": leaves, "clashes": found,
            "tasks": tasks, "done": done_today, "prep": prep, "questions": questions, "review": to_review,
            "now": current, "next": upcoming, "set_last_night": promised_by.startswith(day.isoformat())}


def show_day(con, settings, day):
    today = date.today()
    p = picture(con, settings, day)
    timeline = []
    for e in p["entries"]:
        timeline.append(("entry", e["start"], e))
    for b in p["blocks"]:
        timeline.append(("block", b["start"], b))
    for l in p["leaves"]:
        if not any(x["source"] == "ride" and x["title"] == l["title"] for x in p["entries"]):
            timeline.append(("leave", l["leave"], l))
    timeline.sort(key=lambda t: (t[1], {"leave": 0, "entry": 1, "block": 2}[t[0]]))
    promised = [t for t in p["tasks"] if t["promised"]]
    others = [t for t in p["tasks"] if not t["promised"] and not t["before"]]

    if JSON:
        emit({"now": datetime.now().strftime("%Y-%m-%d %H:%M"), "day": day.isoformat(), "label": long_day(day),
              "today": today.isoformat(),
              "timeline": [dict(kind=k, **(entry_json(x) if k == "entry" else
                                           {"title": x["title"], "start": x["start"].strftime("%Y-%m-%d %H:%M"),
                                            "end": x["end"].strftime("%Y-%m-%d %H:%M"), "block": x["kind"]}
                                           if k == "block" else
                                           {"title": x["title"], "start": x["leave"].strftime("%Y-%m-%d %H:%M"),
                                            "minutes": x["minutes"], "traffic": x["traffic"],
                                            "arrive": hm(x["arrive"]), "place": x["place"]}))
                           for k, _, x in timeline],
              "promised": [task_json(t) for t in promised], "tasks": [task_json(t) for t in others],
              "done": [task_json(t) for t in p["done"]], "todoist": p["todoist"],
              "prep": [{"key": k, "title": k.split("|", 1)[1], "at": k[11:16], "tasks": [task_json(t) for t in v]}
                       for k, v in p["prep"].items()],
              "clashes": [{"who": c["who"], "a": c["a"]["title"], "b": c["b"]["title"], "from": hm(c["from"]),
                           "until": hm(c["until"])} for c in p["clashes"]],
              "warnings": p["warnings"], "questions": p["questions"],
              "review": [entry_json(e) for e in p["review"]],
              "current": entry_json(p["now"]) if p["now"] else None,
              "next": entry_json(p["next"]) if p["next"] else None,
              "leave": next(({"title": l["title"], "leave": hm(l["leave"]), "minutes": l["minutes"],
                              "traffic": l["traffic"]} for l in p["leaves"] if l["leave"] >= datetime.now()), None),
              "setLastNight": p["set_last_night"]}, [])
        return

    appointments = [e for e in p["entries"] if e["source"] != "ride"]
    head = f"{long_day(day)}: " + (f"{len(appointments)} appointment{'s' * (len(appointments) != 1)}"
                                   if appointments else "no appointments")
    head += f", {len(p['tasks'])} task{'s' * (len(p['tasks']) != 1)} open." if p["tasks"] else ", no tasks open."
    lines = [head]
    if promised:
        lines += ["", "Promised" + (" last night" if p["set_last_night"] else "") + ", first thing:"]
        lines += ["  " + task_line(t, today) for t in promised]
    if timeline:
        lines += ["", "The day:"]
    for kind, at, x in timeline:
        if kind == "entry":
            if x["allday"]:
                lines.append(f"  all day      {x['title']} [{x['ref']}]")
                continue
            bits = [f"  {hm(x['start'])}-{hm(x['end'])}  {x['title']}"]
            if x["ref"]:
                bits.append(f"[{x['ref']}]")
            if x["who"] not in ("me", "") and x["source"] != "ride":
                bits.append(f"({x['who']})")
            if x["source"] == "ride" and x["who"] != "me":
                bits.append(f"({x['who']} drives)")
            if x["place"] and x["source"] != "ride":
                bits.append(f"at {x['place']}")
            if x.get("also"):
                bits.append(f"(also in {', '.join(x['also'])})")
            lines.append(" ".join(bits))
        elif kind == "block":
            lines.append(f"  {hm(x['start'])}-{hm(x['end'])}  {x['title']} (kept free)")
        else:
            lines.append(f"  {hm(x['leave'])}        leave for {x['title']}: {minutes_text(x['minutes'])} "
                         f"{'with live traffic' if x['traffic'] else 'by ' + (settings.get('transport') or 'car')}")
    if p["prep"]:
        lines += ["", "Finish before:"]
        for k, rows in p["prep"].items():
            lines.append(f"  {k.split('|', 1)[1]} at {k[11:16]}: " + ", ".join(f"#{r['id']} {r['title']}" for r in rows))
    if others:
        lines += ["", "Tasks:"] + ["  " + task_line(t, today) for t in others]
    if p["todoist"]:
        lines += ["", "In Todoist (tick off with todoist done <n>):"]
        lines += [f"  {t['n']}. {t['content']}" + (f" ({t['when']})" if t.get("when") else "") for t in p["todoist"]]
    if p["clashes"]:
        lines += ["", "Clashes:"]
        for c in p["clashes"]:
            who = "you" if c["who"] == "me" else c["who"]
            lines.append(f"  {c['a']['title']} and {c['b']['title']} overlap from {hm(c['from'])} to "
                         f"{hm(c['until'])} for {who}.")
    doubles = [e for e in p["entries"] if e.get("also")]
    if doubles:
        lines += [""] + [f"{e['title']} at {hm(e['start'])} is planned twice: in {e['calendar']} "
                         f"and {', '.join(e['also'])}." for e in doubles]
    if p["warnings"]:
        lines += [""] + p["warnings"]
    if p["review"]:
        lines += ["", "How did it go? " + "; ".join(f"{e['title']} [{e['ref']}]" for e in p["review"])
                  + ". Ask the owner, then: planner review <ref> --feeling ... --outcome ... --action ..."]
    for q in p["questions"]:
        lines += ["", q["ask"]]
    if day == today and p["next"]:
        lines += ["", next_line(p)]
    emit(None, lines)


def next_line(p):
    e = p["next"]
    line = ""
    if p["now"]:
        line = f"Now: {p['now']['title']} until {hm(p['now']['end'])}. "
    line += f"Next: {e['title']} at {hm(e.get('at') or e['start'])}"
    if e["place"]:
        line += f", {e['place']}"
    line += "."
    leave = next((l for l in p["leaves"] if l["title"] == e["title"]), None)
    if leave:
        line += f" Leave at {hm(leave['leave'])} ({minutes_text(leave['minutes'])})."
    open_prep = p["prep"].get(key_of(e)) if e["ref"] else None
    if open_prep:
        line += " Still to do first: " + ", ".join(f"#{r['id']} {r['title']}" for r in open_prep) + "."
    return line


# --- commands --------------------------------------------------------------------------------------------------

def cmd_today(con, settings, args):
    day = parse_day(args[0]) if args else date.today()
    if not day or day == "later":
        fail(f"Which day is {args[0]}? Say today, tomorrow, a weekday or 2026-10-02.")
    show_day(con, settings, day)


def cmd_next(con, settings, args):
    p = picture(con, settings, date.today())
    if not p["next"]:
        tomorrow = entries_between(con, settings, date.today() + timedelta(days=1), date.today() + timedelta(days=1))
        first = next((e for e in tomorrow if not e["allday"] and mine(e)), None)
        line = (f"Now: {p['now']['title']} until {hm(p['now']['end'])}. " if p["now"] else "") + \
            "Nothing else today." + (f" Tomorrow starts with {first['title']} at {hm(first['start'])}." if first else "")
        emit({"current": entry_json(p["now"]) if p["now"] else None, "next": None}, [line])
        return
    ended = [e for e in p["review"] if datetime.now() - e["end"] < timedelta(hours=2)]
    lines = [next_line(p)]
    if ended:
        lines.append("Just ended: " + ", ".join(f"{e['title']} [{e['ref']}]" for e in ended)
                     + ". Ask how it went, and keep it with planner review.")
    emit({"current": entry_json(p["now"]) if p["now"] else None, "next": entry_json(p["next"]),
          "review": [entry_json(e) for e in ended]}, lines)


def cmd_leave(con, settings, args):
    rest, opts = options(args, set())
    if not (shutil.which("maps") or shutil.which("travel")):
        fail("For the time to leave I use the travel plugin (free) or maps (Google, with traffic). "
             "Install one of them and set your home address there.")
    today = date.today()
    now = datetime.now()
    if rest:
        target, _ = resolve(con, settings, " ".join(rest))
        day = target["start"].date()
    else:
        target, day = None, today
    entries = entries_between(con, settings, day, day)
    entries += rides(con, settings, entries)
    leaves = departures(con, settings, day, entries)
    if target:
        pick = [l for l in leaves if l["for"] == target["ref"] or l["title"] == target["title"]]
        if not pick:
            if not target["place"]:
                fail(f"{target['title']} has no address. Add one in its calendar to know when to leave.")
            t = travel_time(con, settings, None, target["place"], target["start"])
            fail(t.get("error") or f"I cannot find a route to {target['place']}.")
        l = pick[0]
    else:
        ahead = [l for l in leaves if l["arrive"] > now]
        if not ahead:
            emit({"leave": None}, ["Nothing to leave for today."])
            return
        l = ahead[0]
    warn = number(settings, "warn") or 15
    wait = (l["leave"] - now).total_seconds() / 60
    if opts.get("soon") and wait > warn:
        emit({"leave": None, "in": round(wait)}, [f"Not yet: leave for {l['title']} at {hm(l['leave'])}."])
        return
    how = "with live traffic" if l["traffic"] else f"by {settings.get('transport') or 'car'}, without live traffic"
    when = ("now" if -1 <= wait <= 1 else f"in {minutes_text(wait)}" if wait > 0
            else f"{minutes_text(-wait)} ago")
    lines = [f"Leave at {hm(l['leave'])} ({when}) for {l['title']} at {hm(l['arrive'])}, {l['place']}.",
             f"{minutes_text(l['minutes'])} from {l['from']} {how}, {number(settings, 'buffer')} min early."]
    emit({"leave": {"title": l["title"], "at": hm(l["leave"]), "arrive": hm(l["arrive"]), "minutes": l["minutes"],
                    "traffic": l["traffic"], "place": l["place"], "in": round(wait)}}, lines)


def cmd_near(con, settings, args):
    if not args:
        fail("planner near <appointment|address>")
    word = " ".join(args)
    title, address = "", word
    try:
        e, _ = resolve(con, settings, word)
    except Stop:
        if re.fullmatch(r"[cfg][0-9a-f]{1,6}", word.lower()):
            raise
        e = None
    if e:
        if not e["place"]:
            fail(f"{e['title']} has no address.")
        address, title = e["place"], e["title"]
    if not shutil.which("maps"):
        fail("Parking and places to eat come from the maps plugin, with your own Google Maps key. "
             "Install maps, then: maps key ask.")
    found = {}
    for kind, query in (("parking", "parking"), ("quick", "cafe"), ("sit", "restaurant")):
        data = sibling("maps", ["find", query, "--near", address, "-n", "3"])
        if data.get("error"):
            fail(f"Maps could not look it up: {data['error']}")
        found[kind] = data.get("places") or []

    def spot(p):
        bits = [p["name"]]
        if p.get("address"):
            bits.append(p["address"].split(",")[0])
        extra = ", ".join(x for x in (f"{p['rating']}/5" if p.get("rating") else "",
                                      "open now" if p.get("open_now") is True else
                                      "closed now" if p.get("open_now") is False else "") if x)
        return ", ".join(bits) + (f" ({extra})" if extra else "")

    lines = [f"Near {address}" + (f" ({title})" if title else "") + ":",
             "Parking: " + ("; ".join(spot(p) for p in found["parking"]) or "none found."),
             "Quick coffee or a bite: " + ("; ".join(spot(p) for p in found["quick"]) or "none found."),
             "Sit down for a meal: " + ("; ".join(spot(p) for p in found["sit"]) or "none found.")]
    emit({"place": address, "parking": found["parking"], "quick": found["quick"], "quiet": found["sit"]}, lines)


def cmd_add(con, settings, args):
    lines = ["Appointments live in the calendar, not in the planner."]
    if shutil.which("calendar"):
        lines.append('Plan one with: calendar meet "<title>" <day> <time> [--where <address>].')
    else:
        lines.append("Put it in your Google or Outlook calendar, or install the calendar plugin for this house's own.")
    lines.append('Who it is for and who drives go with: planner owner "<word of the title>" <name> --bring me.')
    fail("\n".join(lines))


def cmd_person(con, settings, args):
    if not args:
        fail("planner person <name> [kid|partner|family|team]")
    if args[0] == "remove":
        name = person(con, " ".join(args[1:]), ())
        con.execute("delete from people where name = ?", (name,))
        con.execute("delete from rules where who = ?", (name,))
        con.commit()
        emit({"removed": name}, [f"{name} is off the list."])
        return
    role = args[-1].lower() if len(args) > 1 and args[-1].lower() in ROLES else "family"
    name = " ".join(args[:-1] if len(args) > 1 and args[-1].lower() in ROLES else args).strip()
    if not name or name.lower() in ("me", "family"):
        fail("Give a name, like: planner person Sem kid.")
    con.execute("insert into people (name, role) values (?, ?) on conflict(name) do update set role = excluded.role",
                (name, role))
    con.commit()
    emit({"name": name, "role": role}, [f"{name} ({role}) is on the list."])


def cmd_people(con, settings, args):
    rows = people(con)
    if not rows:
        emit({"people": []}, ["Only you so far. Add the family: planner person Sem kid, planner person Lisa partner."])
        return
    emit({"people": [dict(r) for r in rows]}, ["You, and: " + ", ".join(f"{r['name']} ({r['role']})" for r in rows) + "."])


def cmd_owner(con, settings, args):
    if args and args[0] == "remove":
        what = " ".join(args[1:]).strip().lower()
        gone = con.execute("delete from rules where pattern in (?, ?)", (what, "calendar:" + what)).rowcount
        con.commit()
        if not gone:
            fail(f"Nothing remembered about {what}.")
        emit({"removed": what}, [f"Forgotten: {what}."])
        return
    rest, opts = options(args, {"bring", "pick", "for"})
    if opts.get("for"):
        rest.append(opts["for"])
    if len(rest) < 2 and not (rest and (opts.get("bring") or opts.get("pick"))):
        fail("planner owner <calendar|word> <name|me|family> [--bring <who>] [--pick <who>]")
    who = person(con, rest[-1]) if len(rest) >= 2 else "me"
    what = " ".join(rest[:-1] if len(rest) >= 2 else rest).strip()
    bring = person(con, opts["bring"], ("me",)) if opts.get("bring") else ""
    pick = person(con, opts["pick"], ("me",)) if opts.get("pick") else ""
    today = date.today()
    calendars = {}
    for e in entries_between(con, settings, today, today + timedelta(days=6)):
        for name in [e["calendar"]] + e.get("also", []):
            if name:
                calendars[name.lower()] = name
    if what.lower() in calendars:
        pattern, said = "calendar:" + what.lower(), f"The calendar {calendars[what.lower()]} is"
    else:
        pattern, said = what.lower(), f"Appointments with \"{what}\" are"
    con.execute("insert or replace into rules (pattern, who, bring, pick) values (?, ?, ?, ?)",
                (pattern, who, bring, pick))
    con.commit()
    whose = "yours" if who == "me" else "for the whole family" if who == "family" else who + "'s"
    lines = [f"{said} {whose}. I will not ask again."]
    if bring or pick:
        lines.append(" ".join(x for x in (f"{'You' if bring == 'me' else bring} bring{'' if bring == 'me' else 's'}."
                                          if bring else "",
                                          f"{'You' if pick == 'me' else pick} pick{'' if pick == 'me' else 's'} up."
                                          if pick else "") if x))
    emit({"pattern": pattern, "who": who, "bring": bring, "pick": pick}, lines)


def cmd_owners(con, settings, args):
    found = rules(con)
    if not found:
        emit({"rules": []}, ["Nothing remembered yet about whose calendar is whose."])
        return
    lines = []
    for p, r in sorted(found.items()):
        name = p.removeprefix("calendar:") if p.startswith("calendar:") else f"\"{p}\""
        bits = [f"{name}: {r['who']}", f"brought by {r['bring']}" if r["bring"] else "",
                f"picked up by {r['pick']}" if r["pick"] else ""]
        lines.append(", ".join(b for b in bits if b))
    emit({"rules": list(found.values())}, lines)


def cmd_prep(con, settings, args):
    if not args:
        fail('planner prep <appointment> ["<what to finish first>"]')
    e, _ = resolve(con, settings, args[0])
    key = key_of(e)
    if len(args) > 1:
        title = " ".join(args[1:]).strip()
        day = min(e["start"].date(), max(date.today(), e["start"].date()))
        cur = con.execute("insert into tasks (title, day, before, created) values (?, ?, ?, ?)",
                          (title, day.isoformat(), key, stamp()))
        con.commit()
        emit({"id": cur.lastrowid}, [f"#{cur.lastrowid} {title}: before {e['title']}, {day_name(e['start'].date())} "
                                     f"{hm(e['start'])}."])
        return
    rows = con.execute("select * from tasks where before = ? order by done != '', id", (key,)).fetchall()
    if not rows:
        emit({"tasks": []}, [f"Nothing to prepare for {e['title']} yet."])
        return
    lines = [f"Before {e['title']} ({day_name(e['start'].date())} {hm(e['start'])}):"]
    lines += [f"  {'done' if r['done'] else 'open'}  #{r['id']} {r['title']}" for r in rows]
    emit({"tasks": [task_json(r) for r in rows]}, lines)


def cmd_review(con, settings, args):
    rest, opts = options(args, {"feeling", "outcome", "action"}, multi={"action"})
    if not rest:
        fail('planner review <appointment> [--feeling good] [--outcome "..."] [--action "..."]')
    e, _ = resolve(con, settings, " ".join(rest))
    actions = [a.strip() for a in opts.get("action", []) if a.strip()]
    con.execute("insert or replace into reviews (key, title, feeling, outcome, actions, created) values (?, ?, ?, ?, ?, ?)",
                (key_of(e), e["title"], opts.get("feeling", ""), opts.get("outcome", ""), "\n".join(actions), stamp()))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    ids = []
    for a in actions:
        ids.append(con.execute("insert into tasks (title, day, created) values (?, ?, ?)",
                               (a, tomorrow, stamp())).lastrowid)
    con.commit()
    lines = [f"Kept how {e['title']} went" + (f": {opts['feeling']}" if opts.get("feeling") else "") + "."]
    if ids:
        lines.append("On tomorrow's list: " + ", ".join(f"#{i} {a}" for i, a in zip(ids, actions)) + ".")
    emit({"key": key_of(e), "tasks": ids}, lines)


def cmd_reviews(con, settings, args):
    today = date.today()
    entries = entries_between(con, settings, today - timedelta(days=1), today)
    done = {r["key"] for r in con.execute("select key from reviews")}
    now = datetime.now()
    wait = [e for e in entries if e["evaluate"] and e["end"] <= now and key_of(e) not in done]
    recent = con.execute("select * from reviews order by created desc limit 3").fetchall()
    lines = []
    if wait:
        lines.append("Waiting for \"how was it?\": " + "; ".join(
            f"{e['title']} [{e['ref']}] {day_name(e['start'].date())} {hm(e['start'])}" for e in wait) + ".")
    else:
        lines.append("No appointment is waiting for a review.")
    if not listed(settings, "evaluate"):
        lines.append("Ask after which appointments? planner evaluate on client (or any word in the title).")
    for r in recent:
        lines.append(f"Last: {r['title']}: " + ", ".join(x for x in (r["feeling"], r["outcome"]) if x) + ".")
    emit({"waiting": [entry_json(e) for e in wait]}, lines)


def cmd_evaluate(con, settings, args):
    if len(args) < 2 or args[0] not in ("on", "off"):
        words = listed(settings, "evaluate")
        emit({"words": words}, ["I ask how it went after appointments with: " + ", ".join(words) + "."
                                if words else "I ask after no appointments yet. Say: planner evaluate on client."])
        return
    word = " ".join(args[1:]).strip().lower()
    words = [w for w in listed(settings, "evaluate") if w.lower() != word]
    if args[0] == "on":
        words.append(word)
    keep("evaluate", ", ".join(words))
    emit({"words": words}, [f"{'Asking' if args[0] == 'on' else 'Not asking'} after appointments with \"{word}\"."])


def cmd_task(con, settings, args, promised=False):
    rest, opts = options(join_days(args), {"before"})
    if not rest:
        fail('planner task "<title>" [<day>]' if not promised else 'planner promise "<title>" [<day>]')
    day = parse_day(rest[-1], later_ok=True) if len(rest) > 1 else None
    if day:
        rest = rest[:-1]
    day = day or (date.today() + timedelta(days=1) if promised else date.today())
    before = ""
    if opts.get("before"):
        e, _ = resolve(con, settings, opts["before"])
        before = key_of(e)
        if day != "later" and day > e["start"].date():
            day = e["start"].date()
    title = " ".join(rest).strip()
    cur = con.execute("insert into tasks (title, day, promised, before, created) values (?, ?, ?, ?, ?)",
                      (title, day if day == "later" else day.isoformat(), 1 if promised else 0, before, stamp()))
    con.commit()
    when = "later, when there is room" if day == "later" else day_name(day)
    emit({"id": cur.lastrowid},
         [f"#{cur.lastrowid} {title}: " + (f"promised for {when}; it is on top that morning." if promised
                                            else f"{when}.")])


def cmd_done(con, settings, args, undo=False):
    if not args:
        fail("planner done <#id|title>")
    row = task_row(con, " ".join(args))
    con.execute("update tasks set done = ? where id = ?", ("" if undo else stamp(), row["id"]))
    con.commit()
    left = len(open_tasks(con, date.today()))
    emit({"id": row["id"], "done": not undo, "left": left},
         [f"#{row['id']} {row['title']}: " + ("open again." if undo else f"done. {left} open today.")])


def cmd_drop(con, settings, args):
    if not args:
        fail("planner drop <#id>")
    row = task_row(con, " ".join(args))
    con.execute("delete from tasks where id = ?", (row["id"],))
    con.commit()
    emit({"id": row["id"]}, [f"#{row['id']} {row['title']} is off the list."])


def cmd_move(con, settings, args):
    args = join_days(args)
    if len(args) < 2:
        fail("planner move <#id>[,<#id>] <tomorrow|overmorrow|nextweek|later|<day>>")
    day = parse_day(args[-1], later_ok=True)
    if not day:
        fail(f"Which day is {args[-1]}? Say tomorrow, overmorrow, nextweek, later or a date.")
    ids = [w for w in re.split(r"[,\s]+", " ".join(args[:-1])) if w]
    rows = [task_row(con, w) for w in ids] if all(w.lstrip("#").isdigit() for w in ids) else \
        [task_row(con, " ".join(args[:-1]))]
    for r in rows:
        con.execute("update tasks set day = ?, moved = moved + 1, done = '' where id = ?",
                    (day if day == "later" else day.isoformat(), r["id"]))
    con.commit()
    when = "later" if day == "later" else day_name(day)
    lines = [", ".join(f"#{r['id']} {r['title']}" for r in rows) + f": {when}."]
    often = [r for r in rows if r["moved"] >= 2]
    if often:
        lines.append(", ".join(r["title"] for r in often) + " moved three times now. Still worth doing, "
                     "or make it smaller?")
    emit({"moved": [r["id"] for r in rows], "day": day if day == "later" else day.isoformat()}, lines)


def cmd_tasks(con, settings, args):
    today = date.today()
    if args and parse_day(args[0], later_ok=True) == "later":
        rows = con.execute("select * from tasks where done = '' and day = 'later' order by id").fetchall()
        label = "Later"
    else:
        day = parse_day(args[0]) if args else today
        if not day:
            fail(f"Which day is {args[0]}?")
        rows = open_tasks(con, day) if day == today else con.execute(
            "select * from tasks where done = '' and day = ? order by promised desc, id", (day.isoformat(),)).fetchall()
        label = day_name(day).capitalize()
    if not rows:
        emit({"tasks": []}, [f"{label}: nothing open."])
        return
    emit({"tasks": [task_json(r) for r in rows]}, [f"{label}:"] + ["  " + task_line(r, today) for r in rows])


def cmd_recap(con, settings, args):
    today = date.today()
    now = datetime.now()
    entries = [e for e in entries_between(con, settings, today, today) if mine(e) and not e["allday"]]
    had = [e for e in entries if e["end"] <= now]
    coming = [e for e in entries if e["end"] > now]
    done = con.execute("select * from tasks where done like ? order by done", (f"{today.isoformat()}%",)).fetchall()
    left = open_tasks(con, today)
    reviews = con.execute("select * from reviews where created like ?", (f"{today.isoformat()}%",)).fetchall()
    lines = [f"{long_day(today)}, looking back."]
    lines.append(f"Appointments: {len(had)}" + (": " + ", ".join(e["title"] for e in had) if had else "")
                 + (f" ({len(coming)} still to come)" if coming else "") + ".")
    lines.append(f"Done: {len(done)} task{'s' * (len(done) != 1)}" +
                 (": " + ", ".join(r["title"] for r in done) if done else "") + ".")
    promised = [r for r in con.execute("select * from tasks where promised = 1 and day = ?", (today.isoformat(),))]
    if promised:
        kept = [r for r in promised if r["done"]]
        lines.append(f"Promises: {len(kept)} of {len(promised)} kept.")
    for r in reviews:
        lines.append(f"{r['title']}: " + ", ".join(x for x in (r["feeling"], r["outcome"]) if x) + ".")
    if left:
        lines += ["", f"Still open ({len(left)}):"] + ["  " + task_line(r, today) for r in left]
        lines += ["", "For each: tomorrow, overmorrow, next week or later? planner move <#id> <when>, "
                      "or planner done / planner drop."]
    else:
        lines.append("Nothing left open. Well done.")
    emit({"had": [entry_json(e) for e in had], "done": [task_json(r) for r in done],
          "left": [task_json(r) for r in left], "reviews": [dict(r) for r in reviews]}, lines)


def cmd_tomorrow(con, settings, args):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    p = picture(con, settings, tomorrow)
    entries = [e for e in p["entries"] if not e["allday"]]
    first = next((e for e in entries if mine(e) or e["who"] == "me"), None)
    promised = [t for t in p["tasks"] if t["promised"]]
    others = [t for t in p["tasks"] if not t["promised"]]
    left = open_tasks(con, today)
    lines = [f"Tomorrow, {long_day(tomorrow)}: " + (f"{len(entries)} appointment{'s' * (len(entries) != 1)}"
                                                    if entries else "no appointments") + "."]
    if first:
        leave = next((l for l in p["leaves"] if l["title"] == first["title"]), None)
        lines.append(f"First: {first['title']} at {hm(first.get('at') or first['start'])}" +
                     (f"; leave at {hm(leave['leave'])}" if leave else "") + ".")
    for e in entries:
        if e["source"] == "ride":
            lines.append(f"{hm(e['start'])} {e['title']}" + (f" ({e['who']} drives)" if e["who"] != "me" else "") + ".")
    if promised:
        lines.append("Promised: " + ", ".join(f"#{t['id']} {t['title']}" for t in promised) + ".")
    if others:
        lines.append("Planned: " + ", ".join(f"#{t['id']} {t['title']}" for t in others) + ".")
    if p["prep"]:
        lines.append("Prepare: " + "; ".join(f"{k.split('|', 1)[1]}: " + ", ".join(r["title"] for r in v)
                                              for k, v in p["prep"].items()) + ".")
    for c in p["clashes"]:
        lines.append(f"Clash: {c['a']['title']} and {c['b']['title']} at {hm(c['from'])}.")
    if left:
        lines.append(f"{len(left)} task{'s are' if len(left) != 1 else ' is'} still open today: "
                     "move them first (planner recap).")
    lines.append("Anything you promised someone for tomorrow? planner promise \"<what>\". It is on top in the morning.")
    meta(con, "looked_ahead", f"{tomorrow.isoformat()} {stamp()}")
    emit({"day": tomorrow.isoformat(), "entries": [entry_json(e) for e in entries],
          "promised": [task_json(t) for t in promised], "tasks": [task_json(t) for t in others],
          "left": len(left)}, lines)


def cmd_sources(con, settings, args):
    have = sources()
    what = {"calendar": "this house's own calendar", "calendars": "calendars you follow by link",
            "google": "Google Calendar", "maps": "travel time with traffic, parking and places to eat",
            "travel": "travel time from home", "todoist": "your Todoist tasks"}
    lines = ["Reading: " + ("; ".join(f"{n} ({what[n]})" for n in have if have[n]) or "nothing yet") + "."]
    missing = [n for n in have if not have[n]]
    if missing:
        lines.append("Not in this house: " + ", ".join(missing) + ". Install one by asking Iris.")
    if not (have["calendar"] or have["calendars"] or have["google"]):
        lines.append("Without a calendar plugin the planner has only your tasks and promises.")
    if not (have["maps"] or have["travel"]):
        lines.append("Without travel or maps there is no time to leave.")
    emit({"sources": have}, lines)


COMMANDS = {
    "today": cmd_today, "day": cmd_today, "next": cmd_next, "leave": cmd_leave, "near": cmd_near, "add": cmd_add,
    "person": cmd_person, "people": cmd_people, "owner": cmd_owner, "owners": cmd_owners, "prep": cmd_prep, "review": cmd_review,
    "reviews": cmd_reviews, "evaluate": cmd_evaluate, "task": cmd_task,
    "promise": lambda con, s, a: cmd_task(con, s, a, promised=True), "done": cmd_done,
    "undo": lambda con, s, a: cmd_done(con, s, a, undo=True), "drop": cmd_drop, "move": cmd_move,
    "tasks": cmd_tasks, "recap": cmd_recap, "tomorrow": cmd_tomorrow, "sources": cmd_sources,
}


def main(argv):
    global JSON
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    JSON = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if argv and argv[0] == "settings":
        try:
            settings_command(argv[1:])
        except Stop as stop:
            print(stop)
            return 1
        return 0
    name, rest = (argv[0].lower(), argv[1:]) if argv else ("today", [])
    if name not in COMMANDS:
        if parse_day(name):
            name, rest = "today", argv
        else:
            print(f"planner has no {name}. planner --help lists what it does.")
            return 2
    con = connect()
    try:
        COMMANDS[name](con, values(), rest)
    except Stop as stop:
        if JSON:
            print(json.dumps({"error": str(stop)}, ensure_ascii=False))
        else:
            print(stop)
        return 1
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
