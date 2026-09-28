#!/usr/bin/env python3
"""Every calendar you follow, in one agenda. Iris reads the links; nothing is ever sent from here.

  calendars                             today and tomorrow
  calendars week [days]                 the days ahead (7 by default, at most 90)
  calendars search <text>               in the next 90 days, on title, place or calendar
  calendars feeds                       which calendars are added, and how each one reads
  calendars add "<name>" <link>         add a calendar (an .ics link)
  calendars remove "<name>"             drop one (by name, or by its link)
  calendars refresh                     read the links again now (otherwise up to 30 minutes old)
  calendars settings                    the values as JSON
  calendars settings set <key> <value>  change one value

What a calendar is: a link to an .ics file. A Google calendar has one under Settings, then "Secret address
in iCal format"; Outlook, Apple and Nextcloud hand out a published link of their own, and any .ics on the
web works. The link is a kind of key: keep it to yourself, and share the calendar, not the link.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
FIELDS_FILE = os.path.join(HERE, "settings.json")
CACHE_FILE = os.path.join(HERE, ".feeds.json")
CACHE_TTL = 30 * 60
LOCAL = datetime.now().astimezone().tzinfo
UTC = timezone.utc
DEFAULT = {"days": "7"}
WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
WEEKDAY_NAME = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAME = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MAX_OCCURRENCES = 600


# --- the values the owner set (the form under Integrations reads and writes the same file) --------------------

def fields():
    try:
        with open(FIELDS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [x for x in data.get("fields", []) if isinstance(x, dict) and x.get("key")]
    except (OSError, ValueError):
        return []


def values():
    out = {}
    for f in fields():
        kind = f.get("type")
        if kind == "toggle":
            out[str(f["key"])] = "off"
        elif kind == "choice" and f.get("options"):
            out[str(f["key"])] = str(f["options"][0])
        else:
            out[str(f["key"])] = ""
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
        kept = {}
    kept[str(key)] = str(value)
    tmp = VALUES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kept, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, VALUES_FILE)


def feeds(kept):
    """The calendars: name to link. "Name|link", or just a link."""
    out = []
    for item in str(kept.get("feeds", "")).split(","):
        item = item.strip()
        if not item:
            continue
        name, bar, link = item.partition("|")
        if not bar:
            name, link = "", item
        link = link.strip()
        if link.startswith("webcal://"):
            link = "https://" + link[len("webcal://"):]
        if link:
            out.append((name.strip(), link))
    return out


def as_text(name, link):
    return f"{name}|{link}" if name else link


def short(link):
    clean = re.sub(r"^https?://", "", link)
    return clean if len(clean) <= 46 else clean[:43] + "..."


# --- reading the links (30 minutes of cache, so an answer is quick) ------------------------------------------

def cache_read():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cache_save(cache):
    tmp = CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass   # a cache that cannot be written is a slow answer, not a broken one


def read_feed(link, cache, now, fresh):
    """(the .ics text, a soft complaint). An old copy beats no agenda at all."""
    hit = cache.get(link) if isinstance(cache.get(link), dict) else None
    if hit and not fresh and now - float(hit.get("at", 0) or 0) < CACHE_TTL and hit.get("text"):
        return str(hit["text"]), ""
    try:
        ask = urllib.request.Request(link, headers={"User-Agent": "Iris calendars/1.0", "Accept": "text/calendar, text/plain, */*"})
        with urllib.request.urlopen(ask, timeout=25) as answer:
            raw = answer.read().decode("utf-8", "replace")
    except Exception as problem:   # any failure here: the other calendars still count
        code = getattr(problem, "code", "")
        why = f"{type(problem).__name__} {code}".strip()
        if hit and hit.get("text"):
            return str(hit["text"]), f"{short(link)} could not be read just now ({why}); this is the last copy"
        return "", f"{short(link)} could not be read ({why})"
    if "BEGIN:VCALENDAR" not in raw.upper():
        return "", f"{short(link)} did not hand out a calendar: check the link"
    cache[link] = {"at": now, "text": raw}
    return raw, ""


# --- an .ics file ---------------------------------------------------------------------------------------------

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
    out = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            out.append({"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}.get(text[i + 1], text[i + 1]))
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out).strip()


def moment(params, value):
    """-> ("date", date) or ("dt", aware datetime), or (None, None) for something unreadable."""
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
    clock = time(int(found.group(2)), int(found.group(3)), int(found.group(4) or 0))
    if found.group(5):
        zone = UTC
    else:
        named = params.get("TZID", "")
        try:
            zone = ZoneInfo(named) if named else LOCAL
        except Exception:
            zone = LOCAL
    return "dt", datetime.combine(day, clock, tzinfo=zone)


def as_dt(kind, start):
    """Everything in one space: an all-day date is midnight where the owner is."""
    return datetime.combine(start, time(0, 0), tzinfo=LOCAL) if kind == "date" else start


def length_of(event):
    if event["end"] and event["end"][0] == event["kind"]:
        seconds = (as_dt(*event["end"]) - as_dt(event["kind"], event["start"])).total_seconds()
        if seconds > 0:
            return timedelta(seconds=seconds)
    if event["duration"]:
        found = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", event["duration"].upper())
        if found and any(found.groups()):
            parts = [int(x or 0) for x in found.groups()]
            return timedelta(weeks=parts[0], days=parts[1], hours=parts[2], minutes=parts[3], seconds=parts[4])
    return timedelta(days=1) if event["kind"] == "date" else timedelta(hours=1)


def parse_calendar(text, feed_name):
    """The events in an .ics file, as plain dictionaries."""
    name_of_feed = feed_name
    for line in unfold(text):
        prop, _, value = split_prop(line)
        if prop == "X-WR-CALNAME" and value.strip() and not feed_name:
            name_of_feed = unescape(value)[:60]
            break
    events, current = [], None
    for line in unfold(text):
        prop, params, value = split_prop(line)
        if prop == "BEGIN" and value.strip().upper() == "VEVENT":
            current = {}
        elif prop == "END" and value.strip().upper() == "VEVENT":
            if current is not None:
                event = build_event(current, name_of_feed)
                if event:
                    events.append(event)
            current = None
        elif current is not None:
            current.setdefault(prop, []).append((params, value))
    return events

def build_event(raw, feed_name):
    def first(prop):
        return raw[prop][0] if raw.get(prop) else (None, None)

    if any(unescape(v).upper() == "CANCELLED" for _, v in raw.get("STATUS", [])):
        return None
    params, value = first("DTSTART")
    if params is None:
        return None
    kind, start = moment(params, value)
    if kind is None:
        return None
    end_params, end_value = first("DTEND")
    end = moment(end_params, end_value) if end_params else (None, None)
    summary = unescape(first("SUMMARY")[1] or "") or "(no title)"
    where = unescape(first("LOCATION")[1] or "")
    lines = [unescape(v) for _, v in raw.get("RRULE", []) if v]
    rule = lines[0] if lines else ""
    exdates = set()
    for params, value in raw.get("EXDATE", []):
        for piece in str(value).split(","):
            ex_kind, ex_start = moment(params, piece)
            if ex_kind:
                exdates.add(as_dt(ex_kind, ex_start))
    return {"feed": feed_name, "summary": summary[:120], "where": where[:80],
            "kind": kind, "start": start, "end": end, "duration": (first("DURATION")[1] or "").strip(),
            "rule": rule, "exdates": exdates}


# --- repeating appointments (the rules calendars really use) ---------------------------------------------------

def rule_of(text):
    rule = {}
    for bit in str(text).split(";"):
        key, _, value = bit.partition("=")
        if key.strip():
            rule[key.strip().upper()] = value.strip()
    return rule


def month_start(day):
    return day.replace(day=1)


def add_months(day, count):
    index = day.year * 12 + (day.month - 1) + count
    return date(index // 12, index % 12 + 1, 1)


def day_in_month(first_of_month, day_number, clock):
    days = (add_months(first_of_month, 1) - first_of_month).days
    number = day_number if day_number > 0 else days + 1 + day_number
    if number < 1 or number > days:
        return None
    return datetime.combine(first_of_month.replace(day=number), clock)


def nth_weekday(first_of_month, ordinal, weekday, clock):
    days = (add_months(first_of_month, 1) - first_of_month).days
    if ordinal >= 0:
        offset = (weekday - first_of_month.weekday()) % 7 + 7 * ordinal
        if offset > days - 1:
            return None
    else:
        last = first_of_month.replace(day=days)
        offset = days - 1 - ((last.weekday() - weekday) % 7) + 7 * (ordinal + 1)
        if offset < 0:
            return None
    return datetime.combine(first_of_month + timedelta(days=offset), clock)


def starts(event):
    """When a repeating appointment starts, one at a time, without an end."""
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
    clock = first.timetz()
    byday = [x.strip().upper() for x in rule.get("BYDAY", "").split(",") if x.strip()]
    bymonthday = [int(x) for x in re.findall(r"-?\d+", rule.get("BYMONTHDAY", ""))]
    if freq == "WEEKLY" and every > 0:
        wanted = sorted({WEEKDAY[x[-2:]] for x in byday if x[-2:] in WEEKDAY} or {first.weekday()})
        week_zero = first - timedelta(days=first.weekday())
        step = 0
        while True:
            for day in wanted:
                at = week_zero + timedelta(weeks=step * every, days=day)
                if at >= first:
                    yield at
            step += 1
    elif freq in ("MONTHLY", "YEARLY"):
        picks = []
        for item in byday:
            found = re.fullmatch(r"([+-]?\d)?(MO|TU|WE|TH|FR|SA|SU)", item)
            if found:
                picks.append((int(found.group(1)) if found.group(1) else 1, WEEKDAY[found.group(2)]))
        step = 0
        while True:
            base = month_start(first)
            if freq == "MONTHLY":
                base = add_months(base, step * every)
            else:
                base = add_months(base, step * every * 12)
            if picks:
                for ordinal, day in picks:
                    at = nth_weekday(base, ordinal, day, clock)
                    if at and at >= first:
                        yield at
            else:
                for number in (bymonthday or [first.day]):
                    at = day_in_month(base, number, clock)
                    if at and at >= first:
                        yield at
            step += 1
    else:   # DAILY, and anything else that is simply a step
        wanted = {WEEKDAY[x[-2:]] for x in byday if x[-2:] in WEEKDAY}
        step = timedelta(days=every)
        at = first
        while True:
            if not wanted or at.weekday() in wanted:   # every day, or every working day
                yield at
            at += step


def occurrences(event, window_start, window_end):
    """The moments of this event that touch the window."""
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
        if until and at > until:
            break
        if count is not None and seen >= count:
            break
        seen += 1
        if seen > MAX_OCCURRENCES or at > window_end + timedelta(days=2):
            break
        if at in event["exdates"]:
            continue
        end = at + length
        if end <= window_start:
            continue   # gone before the window opens
        out.append((at, end))
    return out


# --- the agenda ------------------------------------------------------------------------------------------

def collect(days, start_day=None, fresh=False, text=None):
    """Every appointment in the window, with what to say about the calendars."""
    kept = values()
    mine = feeds(kept)
    today = datetime.now(LOCAL).date()
    first_day = start_day or today
    window_start = datetime.combine(first_day, time(0, 0), tzinfo=LOCAL)
    window_end = window_start + timedelta(days=days)
    now = datetime.now(UTC).timestamp()
    cache, agenda, complaints, used = cache_read(), [], [], []
    for name, link in mine:
        raw, complaint = read_feed(link, cache, now, fresh)
        if complaint:
            complaints.append(complaint)
        if not raw:
            continue
        read = parse_calendar(raw, name)
        used.append(name or (read[0]["feed"] if read else short(link)))
        for event in read:
            event["feed"] = event["feed"] or short(link)
            for at, end in occurrences(event, window_start, window_end):
                if end <= window_start:
                    continue
                agenda.append({**event, "at": at, "until": end})
    cache_save(cache)
    agenda.sort(key=lambda e: e["at"])
    if text:
        needle = text.lower()
        agenda = [e for e in agenda if needle in e["summary"].lower() or needle in e["where"].lower() or needle in e["feed"].lower()]
    return {"days": days, "first_day": first_day, "agenda": agenda, "calendars": used, "complaints": complaints}


def day_label(day, today):
    if day == today:
        return f"Today, {WEEKDAY_NAME[day.weekday()]} {day.day} {MONTH_NAME[day.month - 1]}"
    if day == today + timedelta(days=1):
        return f"Tomorrow, {WEEKDAY_NAME[day.weekday()]} {day.day} {MONTH_NAME[day.month - 1]}"
    return f"{WEEKDAY_NAME[day.weekday()]} {day.day} {MONTH_NAME[day.month - 1]}"


def clock_of(event):
    """How the appointment reads in a line: all day, or the hours."""
    if event["kind"] == "date":
        return "all day"
    start, end = event["at"].astimezone(LOCAL), event["until"].astimezone(LOCAL)
    return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}" if end.date() == start.date() else start.strftime("%H:%M")


def line_for(event):
    line = f"  {clock_of(event):<11} {event['summary']}"
    if event["feed"]:
        line += f"  ({event['feed']})"
    if event["where"]:
        line += f"  {event['where']}"
    return line


def print_agenda(view, empty_line=True):
    today = datetime.now(LOCAL).date()
    per_day = {}
    for event in view["agenda"]:
        if event["kind"] == "date":
            day, last = event["at"].date(), (event["until"] - timedelta(days=1)).date()
        else:
            day, last = event["at"].astimezone(LOCAL).date(), event["at"].astimezone(LOCAL).date()
        while day <= last and (day - view["first_day"]).days < view["days"]:
            if day >= view["first_day"]:
                per_day.setdefault(day, []).append(event)
            day += timedelta(days=1)
    printed = 0
    for step in range(view["days"]):
        day = view["first_day"] + timedelta(days=step)
        rows = per_day.get(day, [])
        if not rows and step > 1:
            continue
        print(day_label(day, today))
        if not rows:
            print("  nothing planned" if empty_line else "  -")
        for event in rows:
            print(line_for(event))
            printed += 1
    return printed


def summary_line(view):
    count = len({(e["summary"], e["at"]) for e in view["agenda"]})
    where = ", ".join(view["calendars"]) if view["calendars"] else "no calendar"
    return f"{count} appointment{'s' if count != 1 else ''} in the next {view['days']} day{'s' if view['days'] != 1 else ''}, from {where}."


def no_calendars():
    print("No calendars yet. Add one under Integrations, or say: add my calendar \"Family\" <link>.")
    print("A Google calendar has its link under Settings, then \"Secret address in iCal format\".")


def show(days, start_day=None, fresh=False, text=None, empty_line=True):
    view = collect(days, start_day=start_day, fresh=fresh, text=text)
    if not view["calendars"]:
        no_calendars()
        return 0
    if view["agenda"]:
        print_agenda(view, empty_line)
    elif text:
        print(f"Nothing with \"{text}\" in it in the next {view['days']} days.")
    else:
        print(f"Nothing planned in the next {view['days']} days.")
    print()
    print(summary_line(view))
    for complaint in view["complaints"]:
        print(f"One calendar: {complaint}.")
    return 0


# --- the commands ---------------------------------------------------------------------------------------------

def add(name, link):
    if not link.startswith(("http://", "https://")):
        print("That is not a link: give the .ics address of the calendar, starting with https://")
        return 1
    kept = values()
    mine = feeds(kept)
    if any(existing == link for _, existing in mine):
        print("That calendar is already in the list.")
        return 1
    mine.append((name.strip(), link))
    keep("feeds", ", ".join(as_text(n, l) for n, l in mine))
    view = collect(7)
    label = name.strip() or next((e for e in view["calendars"] if e), short(link))
    print(f"{label} is added. {summary_line(view)}")
    for complaint in view["complaints"]:
        print(f"One calendar: {complaint}.")
    return 0


def remove(what):
    kept = values()
    mine = feeds(kept)
    needle = what.strip().lower()
    kept_back = [(n, l) for n, l in mine if n.lower() != needle and l != what.strip()]
    if len(kept_back) == len(mine):
        print(f"No calendar called \"{what}\". These are added: " + (", ".join(n or short(l) for n, l in mine) or "none"))
        return 1
    keep("feeds", ", ".join(as_text(n, l) for n, l in kept_back))
    print(f"{what} is out of the list. {len(kept_back)} calendar{'s' if len(kept_back) != 1 else ''} left.")
    return 0


def feeds_command(fresh):
    mine = feeds(values())
    if not mine:
        no_calendars()
        return 0
    now = datetime.now(UTC).timestamp()
    cache = cache_read()
    for name, link in mine:
        raw, complaint = read_feed(link, cache, now, fresh)
        label = name
        count = "-"
        if raw:
            read = parse_calendar(raw, name)
            if not label and read:
                label = read[0]["feed"]
            count = str(len(read))
        stale = ""
        hit = cache.get(link)
        if isinstance(hit, dict) and hit.get("at"):
            minutes = int((now - float(hit["at"])) / 60)
            stale = f", read {minutes} min ago" if minutes else ", read just now"
        print(f"{label or short(link)}  {count} appointment{'s' if count != '1' else ''} in the file{stale}\n  {short(link)}")
        if complaint:
            print(f"  {complaint}")
    cache_save(cache)
    print()
    print("Add one with: calendars add \"Name\" <link>. Drop one with: calendars remove \"Name\".")
    return 0


def main(argv):
    what = argv[0] if argv else ""
    rest = argv[1:]

    if what == "settings":
        if not rest:
            print(json.dumps(values(), indent=2, ensure_ascii=False))
            return 0
        if rest[0] == "set" and len(rest) >= 3:
            key, value = rest[1], " ".join(rest[2:])
            keys = {str(f["key"]) for f in fields()} | set(DEFAULT)
            if key not in keys:
                print(f"There is no setting called {key}. These are: {', '.join(sorted(keys))}")
                return 1
            if key == "days":
                if not value.isdigit() or not 1 <= int(value) <= 90:
                    print("Days: a number from 1 to 90.")
                    return 1
            keep(key, value)
            print(f"Kept: {key} is {value}.")
            return 0
        print("settings, or settings set <key> <value>")
        return 1

    if what in ("", "today"):
        return show(2)
    if what == "tomorrow":
        return show(1, start_day=datetime.now(LOCAL).date() + timedelta(days=1))
    if what == "week":
        days = rest[0] if rest and rest[0].isdigit() else str(values()["days"])
        return show(max(1, min(90, int(days))))
    if what == "search":
        if not rest:
            print('Search what? calendars search "dentist"')
            return 1
        return show(90, text=" ".join(rest))
    if what in ("feeds", "calendars"):
        return feeds_command(fresh=False)
    if what == "refresh":
        return show(2, fresh=True)
    if what == "add":
        if len(rest) >= 2 and rest[-1].startswith(("http://", "https://", "webcal://")):
            return add(" ".join(rest[:-1]), rest[-1].replace("webcal://", "https://"))
        if len(rest) == 1:
            return add("", rest[0])
        print('Add like this: calendars add "Family" https://example.com/family.ics')
        return 1
    if what == "remove":
        if not rest:
            print('Which one? calendars remove "Family"')
            return 1
        return remove(" ".join(rest))

    print(__doc__.strip().split("\n\n")[0])
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        os._exit(0)
