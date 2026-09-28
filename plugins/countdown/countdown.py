#!/usr/bin/env python3
"""How long until the days that matter: a holiday, a deadline, and birthdays that come back every year.

  countdown                             every day you keep, the nearest first
  countdown add "<name>" <date>         keep a day: YYYY-MM-DD once, or MM-DD every year (a birthday)
  countdown remove "<name>"             drop one
  countdown until <date>                days from today to any date, without keeping it
  countdown settings                    the values as JSON
  countdown settings set events <list>  replace the whole list, like: Holiday|2026-12-20, Anna|03-14

Dates can also be written as 20-12-2026, 20 Dec 2026 or 14 March. The list lives in values.json.
"""
import json
import os
import re
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
DEFAULT = {"events": ""}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTHS.update({"mrt": 3, "mei": 5, "okt": 10})


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


def parse_date(text):
    """A date as (year or None, month, day). None for the year means every year."""
    t = text.strip().lower().replace("/", "-").replace(".", "-")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
    elif re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{4})", t):
        d, mo, y = map(int, re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{4})", t).groups())
    elif re.fullmatch(r"(\d{1,2})-(\d{1,2})", t):
        mo, d = map(int, re.fullmatch(r"(\d{1,2})-(\d{1,2})", t).groups())
        y = None
    else:
        m = re.fullmatch(r"(\d{1,2})\s+([a-z]+)\s*(\d{4})?", t) or None
        m2 = re.fullmatch(r"([a-z]+)\s+(\d{1,2}),?\s*(\d{4})?", t)
        if m:
            d, name, y = int(m.group(1)), m.group(2), m.group(3)
        elif m2:
            name, d, y = m2.group(1), int(m2.group(2)), m2.group(3)
        else:
            return None
        mo = MONTHS.get(name[:3])
        if not mo:
            return None
        y = int(y) if y else None
    try:
        date(y or 2024, mo, d)
    except ValueError:
        return None
    return y, mo, d


def next_date(y, mo, d):
    if y:
        return date(y, mo, d)
    today = date.today()
    for year in (today.year, today.year + 1, today.year + 2):
        try:
            nxt = date(year, mo, d)
        except ValueError:
            continue  # 29 February in a year without one
        if nxt >= today:
            return nxt
    return None


def events():
    out = []
    for part in values()["events"].split(","):
        name, _, when = part.strip().rpartition("|")
        parsed = parse_date(when) if name else None
        if parsed:
            out.append((name.strip(), when.strip(), parsed))
    return out


def store(items):
    keep("events", ", ".join(f"{n}|{w}" for n, w, _ in items))


def span(days):
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days < 0:
        return f"{-days} days ago"
    text = f"in {days} days"
    if days >= 14:
        weeks, rest = divmod(days, 7)
        text += f" ({weeks} weeks" + (f" and {rest} day{'s' if rest != 1 else ''})" if rest else ")")
    return text


# --- commands -------------------------------------------------------------------------------------

def cmd_list():
    items = events()
    if not items:
        print('No days kept yet. Add one with: countdown add "<name>" <date>.')
        return
    today = date.today()
    rows, past = [], []
    for name, _, (y, mo, d) in items:
        when = next_date(y, mo, d)
        if when is None:
            continue
        days = (when - today).days
        (past if days < 0 else rows).append((days, name, when, y is None))
    rows.sort()
    for days, name, when, yearly in rows:
        again = ", every year" if yearly else ""
        print(f"{name}: {span(days)}, {when.strftime('%a %d %b %Y')}{again}")
    for days, name, when, _ in sorted(past, reverse=True):
        print(f"{name}: was {when.strftime('%d %b %Y')}, {span(days)}")


def cmd_add(args):
    if len(args) < 2:
        sys.exit('countdown add "<name>" <date>')
    # The date is the last one, two or three words; the name is the rest.
    for n in (3, 2, 1):
        if len(args) > n and parse_date(" ".join(args[-n:])):
            name, when = " ".join(args[:-n]).strip(), " ".join(args[-n:])
            break
    else:
        sys.exit("I could not read that date. Use YYYY-MM-DD, or MM-DD for every year.")
    if "|" in name or "," in name:
        sys.exit("A name cannot hold | or a comma.")
    y, mo, d = parse_date(when)
    stored = f"{y:04d}-{mo:02d}-{d:02d}" if y else f"{mo:02d}-{d:02d}"
    items = [e for e in events() if e[0].lower() != name.lower()]
    store(items + [(name, stored, (y, mo, d))])
    nxt = next_date(y, mo, d)
    days = (nxt - date.today()).days
    past = " That day has already been." if days < 0 else ""
    print(f"Keeping {name}: {span(days)}, {nxt.strftime('%a %d %b %Y')}" + (", every year." if not y else ".") + past)


def cmd_remove(args):
    name = " ".join(args).strip().lower()
    items = events()
    kept = [e for e in items if e[0].lower() != name]
    if len(kept) == len(items):
        sys.exit(f"There is no day called {' '.join(args)}.")
    store(kept)
    print(f"Dropped {next(e[0] for e in items if e[0].lower() == name)}.")


def cmd_until(args):
    parsed = parse_date(" ".join(args))
    if not parsed:
        sys.exit("countdown until <date>, like 2026-12-25 or 25 Dec")
    when = next_date(*parsed) if not parsed[0] else date(*parsed)
    days = (when - date.today()).days
    weekdays = sum(1 for i in range(1, days + 1) if date.fromordinal(date.today().toordinal() + i).weekday() < 5) if days > 0 else 0
    extra = f", {weekdays} of them working days" if days > 1 else ""
    print(f"{when.strftime('%a %d %b %Y')} is {span(days)}{extra}.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] != "events":
        sys.exit("countdown settings set events <Name|date, Name|date>")
    raw = " ".join(args[2:])
    bad = [p for p in raw.split(",") if p.strip() and not parse_date(p.strip().rpartition("|")[2])]
    if bad:
        sys.exit(f"I could not read: {', '.join(b.strip() for b in bad)}.")
    keep("events", raw)
    print(f"{len(events())} days kept.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_list()
    elif cmd == "add":
        cmd_add(rest)
    elif cmd == "remove":
        cmd_remove(rest)
    elif cmd == "until":
        cmd_until(rest)
    elif cmd == "settings":
        cmd_settings(rest)
    elif parse_date(" ".join(argv)):
        cmd_until(argv)
    else:
        sys.exit('countdown, countdown add "<name>" <date>, countdown until <date>.')


if __name__ == "__main__":
    main(sys.argv[1:])
