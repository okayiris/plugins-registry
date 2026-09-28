#!/usr/bin/env python3
"""Public holidays in more than a hundred countries, through Nager.Date. No key and no account.

  holidays                              the next public holidays at home
  holidays next [country]               the same, for another country
  holidays year [year] [country]        all public holidays of a year
  holidays today [country]              is today a public holiday
  holidays long [year] [country]        long weekends, and the days off that make one
  holidays countries                    the countries that are known, with their code
  holidays settings                     the values as JSON
  holidays settings set <key> <value>   change one value (country)

A country is its two letter code (NL, BE, DE, US) or its English name.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
COUNTRIES_FILE = os.path.join(HERE, ".countries.json")
API = "https://date.nager.at/api/v3/"
DEFAULT = {"country": "NL"}


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
    tmp = VALUES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, VALUES_FILE)


def get(path, allow_empty=False):
    req = urllib.request.Request(API + path, headers={"User-Agent": "Iris-holidays/1.0",
                                                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode()
            if resp.status == 204 or not body.strip():
                return None if allow_empty else []
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            sys.exit("That country is not known. `holidays countries` shows them.")
        sys.exit(f"The holiday service answered with status {exc.code}. Try again in a minute.")
    except (OSError, ValueError):
        sys.exit("The holiday service did not answer. Try again in a minute.")


def countries():
    try:
        with open(COUNTRIES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data:
            return data
    except (OSError, ValueError):
        pass
    data = get("AvailableCountries")
    try:
        with open(COUNTRIES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass
    return data


def country(text=None):
    text = (text or values()["country"]).strip()
    if len(text) == 2 and text.isalpha():
        code = text.upper()
        try:
            known = {c["countryCode"]: c["name"] for c in countries()}
        except SystemExit:
            known = {}
        return code, known.get(code)
    for c in countries():
        if c["name"].lower() == text.lower():
            return c["countryCode"], c["name"]
    for c in countries():
        if c["name"].lower().startswith(text.lower()):
            return c["countryCode"], c["name"]
    sys.exit(f"{text} is not a country I know. `holidays countries` shows them.")


def split(args):
    """A year and a country, in any order."""
    year, place = None, None
    for a in args:
        if a.isdigit() and len(a) == 4:
            year = int(a)
        else:
            place = a if place is None else f"{place} {a}"
    return year or date.today().year, country(place)


def label(h):
    name = h["localName"]
    if h.get("name") and h["name"] != name:
        name += f" ({h['name']})"
    if not h.get("global", True) and h.get("counties"):
        name += f", only in {', '.join(c.split('-')[-1] for c in h['counties'][:6])}"
    return name


def day(iso):
    d = datetime.fromisoformat(iso).date()
    delta = (d - date.today()).days
    when = d.strftime("%a %d %b %Y")
    if delta == 0:
        return f"{when}, today"
    if delta == 1:
        return f"{when}, tomorrow"
    if 1 < delta < 60:
        return f"{when}, in {delta} days"
    return when


# --- commands -------------------------------------------------------------------------------------

def cmd_next(args):
    code, name = country(" ".join(args) if args else None)
    items = get(f"NextPublicHolidays/{code}")
    items = [h for h in items if "Public" in (h.get("types") or ["Public"])][:6]
    if not items:
        print(f"No public holidays ahead for {name or code}.")
        return
    print(f"The next public holidays in {name or code}:")
    for h in items:
        print(f"  {day(h['date'])}  {label(h)}")


def cmd_year(args):
    year, (code, name) = split(args)
    items = get(f"PublicHolidays/{year}/{code}")
    if not items:
        print(f"No public holidays known for {name or code} in {year}.")
        return
    print(f"Public holidays in {name or code}, {year}:")
    for h in items:
        print(f"  {datetime.fromisoformat(h['date']).strftime('%a %d %b')}  {label(h)}")


def cmd_today(args):
    code, name = country(" ".join(args) if args else None)
    items = get(f"PublicHolidays/{date.today().year}/{code}")
    today = [h for h in items if h["date"] == date.today().isoformat()]
    if today:
        print(f"Yes, today is {label(today[0])} in {name or code}.")
    else:
        print(f"No, today is not a public holiday in {name or code}.")


def cmd_long(args):
    year, (code, name) = split(args)
    items = get(f"LongWeekend/{year}/{code}")
    if not items:
        print(f"No long weekends found for {name or code} in {year}.")
        return
    upcoming = [w for w in items if w["endDate"] >= date.today().isoformat()] or items
    print(f"Long weekends in {name or code}, {year}:")
    for w in upcoming:
        start = datetime.fromisoformat(w["startDate"]).strftime("%a %d %b")
        end = datetime.fromisoformat(w["endDate"]).strftime("%a %d %b")
        extra = ""
        if w.get("needBridgeDay"):
            bridges = w.get("bridgeDays") or []
            days = ", ".join(datetime.fromisoformat(b).strftime("%a %d %b") for b in bridges)
            extra = f", take {days} off" if days else ", with one day off"
        print(f"  {start} to {end}: {w['dayCount']} days{extra}")


def cmd_countries():
    items = sorted(countries(), key=lambda c: c["name"])
    print(f"{len(items)} countries:")
    for c in items:
        print(f"  {c['countryCode']}  {c['name']}")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 3 or args[0] != "set" or args[1] != "country":
        sys.exit("holidays settings set country <code or name>")
    code, name = country(" ".join(args[2:]))
    if code not in {c["countryCode"] for c in countries()}:
        sys.exit(f"{code} is not a country I know. `holidays countries` shows them.")
    keep("country", code)
    print(f"Home is {name or code}.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("next", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "next":
        cmd_next(rest)
    elif cmd == "year":
        cmd_year(rest)
    elif cmd == "today":
        cmd_today(rest)
    elif cmd == "long":
        cmd_long(rest)
    elif cmd == "countries":
        cmd_countries()
    elif cmd == "settings":
        cmd_settings(rest)
    elif cmd.isdigit() and len(cmd) == 4:
        cmd_year(argv)
    else:
        cmd_next(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
