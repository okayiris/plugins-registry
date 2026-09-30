#!/usr/bin/env python3
"""The plan assistant: your day from morning to evening, with the family and the road in it.

Morning
  planner                                   today: promises first, the timeline with meals and breaks,
                                            when to leave, what to prepare, clashes and open questions
  planner day <day>                         the same for another day (tomorrow, friday, 2026-10-02)
  planner next                              what is on now, and the next appointment

On the road
  planner leave [<appointment>] [--soon]    when to leave, with live traffic when there is a TomTom key;
                                            --soon only answers when it is almost time (for a loop)
  planner near <appointment|address>        parking, and a quick or quiet place to eat or drink there

Appointments and the family
  planner add "<title>" <day> <time> [--minutes 60 | --until 11:00] [--where <address>]
              [--for <name>] [--bring <who>] [--pick <who>] [--evaluate]
  planner remove <a3>
  planner person <name> [kid|partner|family|team]    planner person remove <name>    planner people
  planner routine "<title>" --every wed[,fri] --at 16:00 [--minutes 45] [--for <name>] [--where <address>]
              [--bring <who>] [--pick <who>]
  planner routines                          planner routine remove <r2>
  planner owner <calendar|word> <who>       whose calendar (or whose kind of appointment) it is: remembered
  planner owners

Before and after a meeting
  planner prep <appointment> ["<what to finish first>"]
  planner review <appointment> [--feeling <word>] [--outcome "<text>"] [--action "<text>"]...
  planner reviews                           the appointments still waiting for "how was it?"
  planner evaluate on|off <word>            ask afterwards about appointments with this word

Tasks and the evening
  planner task "<title>" [<day>] [--before <appointment>]
  planner promise "<title>" [<day>]         something you promised; tomorrow by default, on top then
  planner done <#id|title>    planner undo <#id>    planner drop <#id>    planner tasks [<day>]
  planner move <#id>[,<#id>] <tomorrow|overmorrow|nextweek|later|<day>>
  planner recap                             what you did today, and what is still open
  planner tomorrow                          a look ahead, ready for the morning

  planner traffic [ask]                     live traffic through your own TomTom key in the vault
  planner settings                          planner settings set <key> <value>

An appointment is its reference (a3, r2, f1c9 from the day's list) or a word of its title. A day is today,
tomorrow, overmorrow, a weekday, nextweek, later, 2026-10-02 or 2-10. Add --json for the window.
"""
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time as clock
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
FIELDS_FILE = os.path.join(HERE, "settings.json")
CACHE_FILE = os.path.join(HERE, ".feeds.json")
CACHE_TTL = 30 * 60


def local_zone():
    """The house's zone with its summer time, so an appointment after the clocks change still lands right."""
    names = [os.environ.get("TZ", "").lstrip(":")]
    try:
        names.append(os.path.realpath("/etc/localtime").split("zoneinfo/", 1)[1])
    except (IndexError, OSError):
        pass
    for name in names:
        try:
            return ZoneInfo(name) if name else None
        except Exception:
            continue
    return datetime.now().astimezone().tzinfo


LOCAL = local_zone() or datetime.now().astimezone().tzinfo
UTC = timezone.utc
AGENT = "Iris planassistant/1.0"
PHOTON = "https://photon.komoot.io/api/"
OSRM = "https://router.project-osrm.org/route/v1/driving/"
TOMTOM = "https://api.tomtom.com/routing/1/calculateRoute/"
TOMTOM_DOMAIN = "api.tomtom.com"
TRAFFIC_ITEM = "planassistant-traffic"
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
ICS_DAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
MAX_OCCURRENCES = 600
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
    if key == "feeds":
        value = ", ".join(x.strip() for x in value.split(",") if x.strip())
    keep(key, value)
    if key == "home" and value:
        place = geocode(connect(), value)
        print(f"Home is {place['label']}." if place else f"Saved, but I cannot find {value} on the map yet.")
        return
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


def owner_rules(con):
    return {r["pattern"]: r["who"] for r in con.execute("select * from owners")}


def owner_of(title, feed, rules, names):
    t = title.lower()
    for pattern in sorted((p for p in rules if not p.startswith("calendar:")), key=len, reverse=True):
        if pattern in t:
            return rules[pattern]
    for name in names:
        if re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", t):
            return name
    if feed:
        return rules.get("calendar:" + feed.lower())
    return None


# --- calendars followed by link (.ics) -------------------------------------------------------------------------

def feeds(settings):
    out = []
    for item in listed(settings, "feeds"):
        name, bar, link = item.partition("|")
        if not bar:
            name, link = "", item
        link = link.strip()
        if link.startswith("webcal://"):
            link = "https://" + link[len("webcal://"):]
        if link:
            out.append((name.strip(), link))
    return out


def cache_read():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cache_save(cache):
    try:
        with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
    except OSError:
        pass


def read_feed(link, cache, now):
    hit = cache.get(link) if isinstance(cache.get(link), dict) else None
    if hit and now - float(hit.get("at", 0) or 0) < CACHE_TTL and hit.get("text"):
        return str(hit["text"]), ""
    try:
        ask = urllib.request.Request(link, headers={"User-Agent": AGENT, "Accept": "text/calendar, */*"})
        with urllib.request.urlopen(ask, timeout=25) as answer:
            raw = answer.read().decode("utf-8", "replace")
    except Exception as problem:   # one calendar that fails leaves the others
        if hit and hit.get("text"):
            return str(hit["text"]), "could not be read just now; this is the last copy"
        return "", f"could not be read ({type(problem).__name__})"
    if "BEGIN:VCALENDAR" not in raw.upper():
        return "", "did not hand out a calendar; check the link"
    cache[link] = {"at": now, "text": raw}
    return raw, ""


def unfold(text):
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def split_prop(line):
    head, colon, value = line.partition(":")
    if not colon:
        return line.strip().upper(), {}, ""
    bits = head.split(";")
    params = {}
    for bit in bits[1:]:
        key, _, val = bit.partition("=")
        params[key.strip().upper()] = val.strip().strip('"')
    return bits[0].strip().upper(), params, value


def unescape(text):
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), text).strip()


def moment(params, value):
    raw = str(value).strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", raw):
        try:
            return "date", datetime.strptime(raw[:8], "%Y%m%d").date()
        except ValueError:
            return None, None
    found = re.fullmatch(r"(\d{8})T(\d{2})(\d{2})(\d{2})?(Z)?", raw)
    if not found:
        return None, None
    day = datetime.strptime(found.group(1), "%Y%m%d").date()
    at = time(int(found.group(2)), int(found.group(3)), int(found.group(4) or 0))
    zone = UTC if found.group(5) else LOCAL
    if not found.group(5) and params.get("TZID"):
        try:
            zone = ZoneInfo(params["TZID"])
        except Exception:
            zone = LOCAL
    return "dt", datetime.combine(day, at, tzinfo=zone)


def as_dt(kind, start):
    return datetime.combine(start, time(0, 0), tzinfo=LOCAL) if kind == "date" else start


def length_of(event):
    if event["end"][0] == event["kind"]:
        seconds = (as_dt(*event["end"]) - as_dt(event["kind"], event["start"])).total_seconds()
        if seconds > 0:
            return timedelta(seconds=seconds)
    found = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", event["duration"].upper())
    if event["duration"] and found and any(found.groups()):
        w, d, h, m, s = (int(x or 0) for x in found.groups())
        return timedelta(weeks=w, days=d, hours=h, minutes=m, seconds=s)
    return timedelta(days=1) if event["kind"] == "date" else timedelta(hours=1)


def parse_calendar(text, feed_name):
    events, current = [], None
    for line in unfold(text):
        prop, params, value = split_prop(line)
        if prop == "X-WR-CALNAME" and value.strip() and not feed_name:
            feed_name = unescape(value)[:60]
        if prop == "BEGIN" and value.strip().upper() == "VEVENT":
            current = {}
        elif prop == "END" and value.strip().upper() == "VEVENT":
            event = build_event(current or {}, feed_name)
            if event:
                events.append(event)
            current = None
        elif current is not None:
            current.setdefault(prop, []).append((params, value))
    return events


def build_event(raw, feed_name):
    def first(prop):
        return raw[prop][0] if raw.get(prop) else ({}, None)

    if any(unescape(v).upper() == "CANCELLED" for _, v in raw.get("STATUS", [])):
        return None
    params, value = first("DTSTART")
    if value is None:
        return None
    kind, start = moment(params, value)
    if kind is None:
        return None
    end_params, end_value = first("DTEND")
    end = moment(end_params, end_value) if end_value else (None, None)
    exdates = set()
    for p, v in raw.get("EXDATE", []):
        for piece in str(v).split(","):
            k, s = moment(p, piece)
            if k:
                exdates.add(as_dt(k, s))
    rules = [unescape(v) for _, v in raw.get("RRULE", []) if v]
    return {"feed": feed_name, "title": (unescape(first("SUMMARY")[1] or "") or "(no title)")[:120],
            "place": unescape(first("LOCATION")[1] or "")[:120], "kind": kind, "start": start, "end": end,
            "duration": (first("DURATION")[1] or "").strip(), "rule": rules[0] if rules else "",
            "exdates": exdates}


def rule_of(text):
    rule = {}
    for bit in str(text).split(";"):
        key, _, value = bit.partition("=")
        if key.strip():
            rule[key.strip().upper()] = value.strip()
    return rule


def add_months(day, count):
    index = day.year * 12 + (day.month - 1) + count
    return date(index // 12, index % 12 + 1, 1)


def starts(event):
    first = as_dt(event["kind"], event["start"])
    if not event["rule"]:
        yield first
        return
    rule = rule_of(event["rule"])
    freq = rule.get("FREQ", "").upper()
    try:
        every = max(1, int(rule.get("INTERVAL", "1")))
    except ValueError:
        every = 1
    byday = [x.strip().upper() for x in rule.get("BYDAY", "").split(",") if x.strip()]
    if freq == "WEEKLY":
        wanted = sorted({ICS_DAY[x[-2:]] for x in byday if x[-2:] in ICS_DAY} or {first.weekday()})
        week_zero = first - timedelta(days=first.weekday())
        step = 0
        while True:
            for day in wanted:
                at = week_zero + timedelta(weeks=step * every, days=day)
                if at >= first:
                    yield at
            step += 1
    elif freq in ("MONTHLY", "YEARLY"):
        step = 0
        while True:
            base = add_months(first.date().replace(day=1), step * every * (12 if freq == "YEARLY" else 1))
            try:
                at = datetime.combine(base.replace(day=first.day), first.timetz())
                if at >= first:
                    yield at
            except ValueError:
                pass
            step += 1
    else:
        wanted = {ICS_DAY[x[-2:]] for x in byday if x[-2:] in ICS_DAY}
        at = first
        while True:
            if not wanted or at.weekday() in wanted:
                yield at
            at += timedelta(days=every)


def occurrences(event, window_start, window_end):
    rule = rule_of(event["rule"])
    until = None
    if rule.get("UNTIL"):
        kind, end = moment({}, rule["UNTIL"])
        if kind:
            until = as_dt(kind, end)
    try:
        count = int(rule.get("COUNT", ""))
    except ValueError:
        count = None
    length = length_of(event)
    out, seen = [], 0
    for at in starts(event):
        if (until and at > until) or (count is not None and seen >= count):
            break
        seen += 1
        if seen > MAX_OCCURRENCES or at > window_end:
            break
        if at in event["exdates"] or at + length <= window_start:
            continue
        out.append((at, at + length))
    return out


def feed_entries(settings, first_day, last_day, notes):
    links = feeds(settings)
    if not links:
        return []
    cache = cache_read()
    now = clock.time()
    lo = datetime.combine(first_day, time(0, 0), tzinfo=LOCAL)
    hi = datetime.combine(last_day + timedelta(days=1), time(0, 0), tzinfo=LOCAL)
    out = []
    for name, link in links:
        text, complaint = read_feed(link, cache, now)
        if complaint:
            notes.append(f"Calendar {name or link[:40]} {complaint}.")
        for event in parse_calendar(text, name) if text else []:
            for at, end in occurrences(event, lo, hi):
                if at >= hi:
                    continue
                s = at.astimezone(LOCAL).replace(tzinfo=None)
                e = end.astimezone(LOCAL).replace(tzinfo=None)
                out.append({"title": event["title"], "start": s, "end": e, "place": event["place"],
                            "feed": event["feed"] or name, "allday": event["kind"] == "date", "source": "feed"})
    cache_save(cache)
    return out


# --- the map: addresses, routes, parking and food ----------------------------------------------------------------

def http_json(url, timeout=25):
    ask = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(ask, timeout=timeout) as answer:
            return json.loads(answer.read().decode("utf-8", "replace"))
    except (OSError, ValueError, urllib.error.URLError):
        return None


def geocode(con, address, near=None):
    address = " ".join(str(address or "").split())
    if not address:
        return None
    row = con.execute("select * from places where address = ?", (address,)).fetchone()
    if row:
        return dict(row) if row["lat"] is not None else None
    query = {"q": address, "limit": 1}
    if near:
        query.update({"lat": round(near["lat"], 3), "lon": round(near["lon"], 3)})
    data = http_json(PHOTON + "?" + urllib.parse.urlencode(query))
    if data is None:
        return None   # no answer now: try again next time
    feats = data.get("features") or []
    place = None
    if feats:
        lon, lat = feats[0]["geometry"]["coordinates"][:2]
        p = feats[0].get("properties") or {}
        street = " ".join(str(x) for x in (p.get("street"), p.get("housenumber")) if x)
        label = ", ".join(str(x) for x in (p.get("name"), street, p.get("city")) if x) or address
        place = {"address": address, "lat": lat, "lon": lon, "label": label}
    con.execute("insert or replace into places (address, lat, lon, label) values (?, ?, ?, ?)",
                (address, place and place["lat"], place and place["lon"], place["label"] if place else ""))
    con.commit()
    return place


def home_place(con, settings):
    return geocode(con, settings.get("home", ""))


def vault_bin():
    return os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN") or shutil.which("kluis") or shutil.which("vault")


def traffic_item():
    exe = vault_bin()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in r.stdout.splitlines():
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p]
        if len(parts) >= 3 and (parts[0] == TRAFFIC_ITEM or parts[2].strip().lower().endswith(TOMTOM_DOMAIN)):
            return parts[0]
    return None


def route_tomtom(item, a, b, arrive):
    coords = f"{a['lat']:.5f},{a['lon']:.5f}:{b['lat']:.5f},{b['lon']:.5f}"
    query = "&".join(["key={g}", "traffic=true", "travelMode=car",
                      "arriveAt=" + urllib.parse.quote(arrive.strftime("%Y-%m-%dT%H:%M:00"))])
    try:
        r = subprocess.run([vault_bin(), "doe", item, "GET", TOMTOM + coords + "/json?" + query],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    first, _, rest = (r.stdout or "").partition("\n")
    if not re.match(r"status\s+200", first.strip()):
        return None
    try:
        summary = json.loads(rest)["routes"][0]["summary"]
        return {"seconds": float(summary["travelTimeInSeconds"]), "meters": float(summary["lengthInMeters"]),
                "traffic": True}
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def route(con, settings, a, b, arrive):
    """Travel time from a to b for the way the owner travels: {seconds, meters, traffic}, or None."""
    mode = settings.get("transport") or "car"
    key = f"{a['lat']:.4f},{a['lon']:.4f}>{b['lat']:.4f},{b['lon']:.4f}"
    item = traffic_item() if mode == "car" else None
    if item:
        row = con.execute("select * from routes where key = ? and traffic = 1", (key + "|" + hm(arrive),)).fetchone()
        if row and clock.time() - row["at"] < 20 * 60:
            return dict(row)
        live = route_tomtom(item, a, b, arrive)
        if live:
            con.execute("insert or replace into routes values (?, ?, ?, 1, ?)",
                        (key + "|" + hm(arrive), live["seconds"], live["meters"], clock.time()))
            con.commit()
            return live
    row = con.execute("select * from routes where key = ? and traffic = 0", (key,)).fetchone()
    if row:
        found = dict(row)
    else:
        data = http_json(f"{OSRM}{a['lon']:.5f},{a['lat']:.5f};{b['lon']:.5f},{b['lat']:.5f}?overview=false")
        if not data or data.get("code") != "Ok" or not data.get("routes"):
            return None
        found = {"seconds": float(data["routes"][0]["duration"]), "meters": float(data["routes"][0]["distance"]),
                 "traffic": 0}
        con.execute("insert or replace into routes values (?, ?, ?, 0, ?)",
                    (key, found["seconds"], found["meters"], clock.time()))
        con.commit()
    if mode == "bike":
        found["seconds"] = found["meters"] / 1000 / 15 * 3600
    elif mode == "walk":
        found["seconds"] = found["meters"] / 1000 / 5 * 3600
    found["traffic"] = False
    return found


def distance(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2 - lat1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def around(place, tags, limit=10):
    """Named places of a kind within about 600 metres, nearest first."""
    query = [("lat", f"{place['lat']:.5f}"), ("lon", f"{place['lon']:.5f}"), ("radius", "0.6"),
             ("limit", str(limit))] + [("osm_tag", t) for t in tags]
    data = http_json(PHOTON.replace("/api/", "/reverse") + "?" + urllib.parse.urlencode(query))
    out = []
    for f in (data or {}).get("features") or []:
        p = f.get("properties") or {}
        name = p.get("name") or ""
        if not name or re.match(r"(?i)(k\+r|kiss|halen en brengen|drop.?off)", name):
            continue   # a spot to drop someone off is not a place to park
        lon, lat = f["geometry"]["coordinates"][:2]
        spot = {"name": name, "kind": p.get("osm_value", ""), "lat": lat, "lon": lon,
                "street": " ".join(str(x) for x in (p.get("street"), p.get("housenumber")) if x)}
        spot["meters"] = round(distance(place, spot))
        if all(o["name"] != name for o in out):
            out.append(spot)
    return sorted(out, key=lambda s: s["meters"])


# --- the day: appointments from everywhere, the children's rides, meals and breaks ------------------------------

def key_of(entry):
    return f"{entry['start']:%Y-%m-%d %H:%M}|{entry['title']}"


def entries_between(con, settings, first_day, last_day, notes=None):
    """Every appointment from first_day to last_day, sorted, with who it is for."""
    notes = notes if notes is not None else []
    out = []
    lo, hi = f"{first_day} 00:00", f"{last_day + timedelta(days=1)} 00:00"
    for r in con.execute("select * from appointments where starts < ? and ends > ? order by starts", (hi, lo)):
        out.append({"ref": f"a{r['id']}", "title": r["title"], "start": datetime.strptime(r["starts"], "%Y-%m-%d %H:%M"),
                    "end": datetime.strptime(r["ends"], "%Y-%m-%d %H:%M"), "place": r["place"], "who": r["who"],
                    "bring": r["bring"], "pick": r["pick"], "evaluate": bool(r["evaluate"]), "source": "own",
                    "feed": "", "allday": False, "note": r["note"]})
    day = first_day
    routines = con.execute("select * from routines").fetchall()
    while day <= last_day:
        for r in routines:
            if str(day.weekday()) in r["days"].split(","):
                s = datetime.combine(day, datetime.strptime(r["at"], "%H:%M").time())
                out.append({"ref": f"r{r['id']}", "title": r["title"], "start": s,
                            "end": s + timedelta(minutes=r["minutes"]), "place": r["place"], "who": r["who"],
                            "bring": r["bring"], "pick": r["pick"], "evaluate": False, "source": "routine",
                            "feed": "", "allday": False, "note": ""})
        day += timedelta(days=1)
    rules = owner_rules(con)
    family = people(con)
    names = [p["name"] for p in family]
    words = [w.lower() for w in listed(settings, "evaluate")]
    for e in feed_entries(settings, first_day, last_day, notes):
        who = owner_of(e["title"], e["feed"], rules, names)
        e.update({"ref": "f" + hashlib.sha1(key_of(e).encode()).hexdigest()[:4],
                  "who": who or ("me" if not family else ""), "bring": "", "pick": "", "evaluate": False,
                  "note": ""})
        out.append(e)
    seen = {}
    for e in sorted(out, key=lambda x: (x["start"], x["source"] != "own", x["title"].lower())):
        if not e["evaluate"] and any(w in e["title"].lower() for w in words):
            e["evaluate"] = True
        same = seen.get((e["start"], e["title"].lower()))
        if same:   # one appointment in two calendars
            same.setdefault("also", []).append(e["feed"] or e["source"])
            continue
        seen[(e["start"], e["title"].lower())] = e
    lo_dt, hi_dt = datetime.combine(first_day, time(0, 0)), datetime.combine(last_day + timedelta(days=1), time(0, 0))
    return [e for e in seen.values() if e["end"] > lo_dt and e["start"] < hi_dt]


def mine(e):
    return e["who"] in ("me", "family", "")


def rides(con, settings, entries):
    """Bringing and picking up: for the children's appointments, and for anyone who is driven."""
    home = None
    out = []
    for e in entries:
        if e["allday"] or not (e["bring"] or e["pick"]):
            continue
        minutes = 15
        if e["place"]:
            home = home or home_place(con, settings)
            there = geocode(con, e["place"], home) if home else None
            if home and there:
                r = route(con, settings, home, there, e["start"])
                if r:
                    minutes = max(5, round(r["seconds"] / 60))
        for kind, driver in (("bring", e["bring"]), ("pick", e["pick"])):
            if not driver:
                continue
            at = e["start"] if kind == "bring" else e["end"]
            what = (f"Bring {e['who']} to {e['title']}" if kind == "bring" else f"Pick up {e['who']} from {e['title']}") \
                if e["who"] not in ("me", "family", "") else f"{kind.capitalize()} for {e['title']}"
            out.append({"ref": "", "title": what, "start": at - timedelta(minutes=minutes),
                        "end": at + timedelta(minutes=minutes), "at": at, "place": e["place"], "who": driver,
                        "ride": kind, "for": e["ref"], "source": "ride", "allday": False, "evaluate": False,
                        "bring": "", "pick": "", "feed": "", "note": ""})
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
    home = home_place(con, settings)
    if not home:
        return out
    buffer = number(settings, "buffer")
    extra = 5 if (settings.get("transport") or "car") == "car" else 0
    last_place, last_end = home, None
    for e in sorted((x for x in entries if not x["allday"] and x["start"].date() == day
                     and (mine(x) or x["who"] == "me")), key=lambda x: x["start"]):
        if not e["place"]:
            continue
        there = geocode(con, e["place"], home)
        if not there:
            continue
        arrive = e.get("at") or e["start"]
        origin = last_place if last_end and arrive - last_end < timedelta(hours=3) else home
        if origin is not there and abs(origin["lat"] - there["lat"]) + abs(origin["lon"] - there["lon"]) > 0.0005:
            r = route(con, settings, origin, there, arrive)
            if r:
                travel = r["seconds"] / 60 + extra
                leave = arrive - timedelta(minutes=round(travel) + buffer)
                out.append({"for": e["ref"] or e["title"], "title": e["title"], "leave": leave, "arrive": arrive,
                            "minutes": round(travel), "traffic": bool(r["traffic"]), "place": there["label"],
                            "from": "home" if origin is home else "your previous appointment"})
        last_place, last_end = there, (e["at"] if e["source"] == "ride" else e["end"])
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
            "source": e["source"], "feed": e["feed"], "allday": e["allday"], "evaluate": e["evaluate"],
            "ride": e.get("ride", ""), "at": e["at"].strftime("%H:%M") if e.get("at") else "",
            "also": e.get("also", []), "key": key_of(e)}


def picture(con, settings, day):
    today = date.today()
    now = datetime.now()
    notes = []
    entries = entries_between(con, settings, day, day, notes)
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
        for e in entries_between(con, settings, day, day + timedelta(days=1)):
            if e["source"] == "feed" and not e["who"]:
                unknown.setdefault(e["feed"] or "(no name)", e)
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
    return {"entries": entries, "blocks": meals, "warnings": warnings + notes, "leaves": leaves, "clashes": found,
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
              "done": [task_json(t) for t in p["done"]],
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
    if p["clashes"]:
        lines += ["", "Clashes:"]
        for c in p["clashes"]:
            who = "you" if c["who"] == "me" else c["who"]
            lines.append(f"  {c['a']['title']} and {c['b']['title']} overlap from {hm(c['from'])} to "
                         f"{hm(c['until'])} for {who}.")
    doubles = [e for e in p["entries"] if e.get("also")]
    if doubles:
        lines += [""] + [f"{e['title']} at {hm(e['start'])} is planned twice: in {e['feed'] or 'your own list'} "
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
    home = home_place(con, settings)
    if not home:
        fail("I need your home address first: planner settings set home \"<street number, town>\".")
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
            fail(f"{target['title']} has no address I can find, so I cannot say when to leave."
                 if target["place"] else f"{target['title']} has no address. Add one to know when to leave.")
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
    home = home_place(con, settings)
    title, address = "", word
    try:
        e, _ = resolve(con, settings, word)
    except Stop:
        if re.fullmatch(r"[afr][0-9a-f]{1,6}", word.lower()):
            raise
        e = None
    if e:
        if not e["place"]:
            fail(f"{e['title']} has no address.")
        address, title = e["place"], e["title"]
    place = geocode(con, address, home)
    if not place:
        fail(f"I cannot find {address} on the map.")
    parking = around(place, ["amenity:parking"])[:3]
    quick = around(place, ["amenity:cafe", "amenity:fast_food"])[:3]
    quiet = around(place, ["amenity:restaurant"])[:3]

    def spot(s):
        return f"{s['name']}" + (f", {s['street']}" if s["street"] else "") + f" ({s['meters']} m, " \
               f"{minutes_text(s['meters'] / 80)} walk)"

    lines = [f"Near {place['label']}" + (f" ({title})" if title else "") + ":"]
    lines.append("Parking: " + ("; ".join(spot(s) for s in parking) if parking else "none on the map close by."))
    lines.append("Quick coffee or a bite: " + ("; ".join(spot(s) for s in quick) if quick else "nothing close by."))
    lines.append("Sit down for a meal: " + ("; ".join(spot(s) for s in quiet) if quiet else "nothing close by."))
    emit({"place": place["label"], "parking": parking, "quick": quick, "quiet": quiet}, lines)


def when_and_length(con, args, opts):
    if len(args) < 2:
        fail("Give a day and a time, like: tomorrow 14:30.")
    day = parse_day(args[0])
    at = parse_time(args[1])
    if not day or day == "later":
        fail(f"Which day is {args[0]}?")
    if not at:
        fail(f"{args[1]} is not a time; say it like 14:30.")
    start = datetime.combine(day, at)
    if opts.get("until"):
        until = parse_time(opts["until"])
        if not until or datetime.combine(day, until) <= start:
            fail("--until is a time after the start, like 11:00.")
        end = datetime.combine(day, until)
    else:
        try:
            end = start + timedelta(minutes=max(5, int(opts.get("minutes") or 60)))
        except ValueError:
            fail("--minutes is a number, like 45.")
    return start, end


def cmd_add(con, settings, args):
    rest, opts = options(join_days(args), {"minutes", "until", "where", "for", "bring", "pick", "note"})
    if len(rest) < 3:
        fail('planner add "<title>" <day> <time> [--minutes 60] [--where <address>] [--for <name>]')
    title = " ".join(rest[:-2]).strip()
    start, end = when_and_length(con, rest[-2:], opts)
    who = person(con, opts["for"]) if opts.get("for") else "me"
    bring = person(con, opts["bring"], ("me",)) if opts.get("bring") else ""
    pick = person(con, opts["pick"], ("me",)) if opts.get("pick") else ""
    cur = con.execute("insert into appointments (title, starts, ends, place, who, bring, pick, evaluate, note, created) "
                      "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (title, start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
                       opts.get("where", ""), who, bring, pick, 1 if opts.get("evaluate") else 0,
                       opts.get("note", ""), stamp()))
    con.commit()
    ref = f"a{cur.lastrowid}"
    entries = entries_between(con, settings, start.date(), start.date())
    entries += rides(con, settings, entries)
    mineclash = [c for c in clashes(con, entries) if ref in (c["a"]["ref"], c["b"]["ref"], c["a"].get("for"),
                                                             c["b"].get("for"))]
    lines = [f"Planned [{ref}] {title}, {day_name(start.date())} {hm(start)}-{hm(end)}"
             + (f" at {opts['where']}" if opts.get("where") else "") + (f" for {who}" if who != "me" else "") + "."]
    for kind, driver in (("brings", bring), ("picks up", pick)):
        if driver:
            lines.append(f"{'You' if driver == 'me' else driver} {kind} {who if who != 'me' else ''}".rstrip() + ".")
    for c in mineclash:
        other = c["b"] if c["a"]["ref"] == ref or c["a"].get("for") == ref else c["a"]
        lines.append(f"Careful: it overlaps with {other['title']} ({hm(other['start'])}-{hm(other['end'])}) for "
                     f"{'you' if c['who'] == 'me' else c['who']}.")
    emit({"ref": ref, "clashes": len(mineclash)}, lines)


def cmd_remove(con, settings, args):
    if not args or not re.fullmatch(r"a\d+", args[0].lower()):
        fail("planner remove <a3>: only appointments you added here; a calendar's own go in that calendar.")
    row = con.execute("select * from appointments where id = ?", (int(args[0][1:]),)).fetchone()
    if not row:
        fail(f"There is no appointment {args[0]}.")
    con.execute("delete from appointments where id = ?", (row["id"],))
    con.commit()
    emit({"removed": args[0]}, [f"Removed {row['title']} ({row['starts']})."])


def cmd_person(con, settings, args):
    if not args:
        fail("planner person <name> [kid|partner|family|team]")
    if args[0] == "remove":
        name = person(con, " ".join(args[1:]), ())
        con.execute("delete from people where name = ?", (name,))
        con.execute("delete from owners where who = ?", (name,))
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


def cmd_routine(con, settings, args):
    if args and args[0] == "remove":
        ref = (args[1] if len(args) > 1 else "").lower()
        if not re.fullmatch(r"r\d+", ref):
            fail("planner routine remove <r2>")
        row = con.execute("select * from routines where id = ?", (int(ref[1:]),)).fetchone()
        if not row:
            fail(f"There is no routine {ref}.")
        con.execute("delete from routines where id = ?", (row["id"],))
        con.commit()
        emit({"removed": ref}, [f"{row['title']} is no longer planned every week."])
        return
    rest, opts = options(args, {"every", "at", "minutes", "where", "for", "bring", "pick"})
    title = " ".join(rest).strip()
    if not title or not opts.get("every") or not opts.get("at"):
        fail('planner routine "<title>" --every wed[,fri] --at 16:00 [--minutes 45] [--for <name>]')
    days = []
    for w in re.split(r"[,\s]+", str(opts["every"]).lower()):
        if w and w.removeprefix("every") not in WEEKDAY_WORDS:
            fail(f"{w} is not a weekday.")
        if w:
            days.append(WEEKDAY_WORDS[w.removeprefix("every")])
    at = parse_time(opts["at"])
    if not at:
        fail("--at is a time, like 16:00.")
    try:
        minutes = max(5, int(opts.get("minutes") or 60))
    except ValueError:
        fail("--minutes is a number, like 45.")
    who = person(con, opts["for"]) if opts.get("for") else "me"
    bring = person(con, opts["bring"], ("me",)) if opts.get("bring") else ""
    pick = person(con, opts["pick"], ("me",)) if opts.get("pick") else ""
    cur = con.execute("insert into routines (title, who, days, at, minutes, place, bring, pick, created) "
                      "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (title, who, ",".join(str(d) for d in sorted(set(days))), at.strftime("%H:%M"), minutes,
                       opts.get("where", ""), bring, pick, stamp()))
    con.commit()
    names = " and ".join(WEEKDAYS[d].capitalize() for d in sorted(set(days)))
    lines = [f"[r{cur.lastrowid}] {title}" + (f" for {who}" if who != "me" else "") +
             f" every {names} at {at.strftime('%H:%M')} ({minutes} min)."]
    if bring or pick:
        lines.append(" ".join(x for x in (f"{'You' if bring == 'me' else bring} bring{'s' if bring != 'me' else ''}."
                                          if bring else "",
                                          f"{'You' if pick == 'me' else pick} pick{'s' if pick != 'me' else ''} up."
                                          if pick else "") if x))
    emit({"ref": f"r{cur.lastrowid}"}, lines)


def cmd_routines(con, settings, args):
    rows = con.execute("select * from routines order by days, at").fetchall()
    if not rows:
        emit({"routines": []}, ['No weekly routines yet. Like: planner routine "Swimming" --for Sem --every wed '
                                '--at 16:00 --bring me.'])
        return
    lines = []
    for r in rows:
        days = " and ".join(WEEKDAYS[int(d)].capitalize() for d in r["days"].split(","))
        bits = [f"[r{r['id']}] {r['title']}", f"({r['who']})" if r["who"] != "me" else "", f"{days} {r['at']},",
                f"{r['minutes']} min", f"at {r['place']}" if r["place"] else "",
                f"brought by {r['bring']}" if r["bring"] else "", f"picked up by {r['pick']}" if r["pick"] else ""]
        lines.append(" ".join(b for b in bits if b))
    emit({"routines": [dict(r) for r in rows]}, lines)


def cmd_owner(con, settings, args):
    if len(args) < 2:
        fail("planner owner <calendar|word> <name|me|family>")
    who = person(con, args[-1])
    what = " ".join(args[:-1]).strip()
    names = {n.lower(): n for n, _ in feeds(settings) if n}
    if what.lower() in names:
        pattern, said = "calendar:" + what.lower(), f"The calendar {names[what.lower()]}"
    else:
        pattern, said = what.lower(), f"Appointments with \"{what}\""
    con.execute("insert or replace into owners (pattern, who) values (?, ?)", (pattern, who))
    con.commit()
    emit({"pattern": pattern, "who": who},
         [f"{said} {'are' if said.startswith('Appointments') else 'is'} "
          f"{'yours' if who == 'me' else 'for the whole family' if who == 'family' else who + chr(39) + 's'}. "
          "I will not ask again."])


def cmd_owners(con, settings, args):
    rows = owner_rules(con)
    if not rows:
        emit({"owners": {}}, ["Nothing remembered yet about whose calendar is whose."])
        return
    emit({"owners": rows}, [f"{p.removeprefix('calendar:') if p.startswith('calendar:') else chr(34) + p + chr(34)}"
                            f": {w}" for p, w in sorted(rows.items())])


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


def cmd_traffic(con, settings, args):
    if args and args[0] == "ask":
        exe = vault_bin()
        if not exe:
            fail("The vault is not on this system.")
        r = subprocess.run([exe, "vraag", TRAFFIC_ITEM, "--domein", TOMTOM_DOMAIN, "TomTom Routing API key"],
                           capture_output=True, text=True, timeout=240)
        if r.returncode != 0:
            fail((r.stderr or r.stdout).strip() or "The vault did not save a key.")
        print("A window opens to paste your TomTom key; it goes straight into the vault. "
              "From then on the time to leave counts live traffic.")
        return
    item = traffic_item()
    emit({"traffic": bool(item)}, [f"Live traffic through TomTom (\"{item}\" in the vault)." if item else
                                   "Travel times without live traffic (OSRM). For traffic: a free TomTom key "
                                   "from developer.tomtom.com, then: planner traffic ask."])


COMMANDS = {
    "today": cmd_today, "day": cmd_today, "next": cmd_next, "leave": cmd_leave, "near": cmd_near, "add": cmd_add,
    "remove": cmd_remove, "person": cmd_person, "people": cmd_people, "routine": cmd_routine,
    "routines": cmd_routines, "owner": cmd_owner, "owners": cmd_owners, "prep": cmd_prep, "review": cmd_review,
    "reviews": cmd_reviews, "evaluate": cmd_evaluate, "task": cmd_task,
    "promise": lambda con, s, a: cmd_task(con, s, a, promised=True), "done": cmd_done,
    "undo": lambda con, s, a: cmd_done(con, s, a, undo=True), "drop": cmd_drop, "move": cmd_move,
    "tasks": cmd_tasks, "recap": cmd_recap, "tomorrow": cmd_tomorrow, "traffic": cmd_traffic,
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
