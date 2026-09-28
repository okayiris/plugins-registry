#!/usr/bin/env python3
"""The time anywhere, and a meeting time in other places. Works offline from the time zone database.

  worldclock                            the time now in the places you keep
  worldclock <place>                    the time now in one place
  worldclock at <time> [in <place>]     that time in your places (like: at 15:00 in Tokyo)
  worldclock meet [places]              the hours when it is working time everywhere
  worldclock add <place>                keep a place
  worldclock remove <place>             drop a place
  worldclock settings                   the values as JSON
  worldclock settings set <key> <value> change one value (places)

A place is a city (Tokyo, New York, San Francisco), a time zone (Europe/Amsterdam) or UTC.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
DEFAULT = {"places": "London, New York, Tokyo"}
WORK = (9, 17)

# Cities people say that are not the name of a time zone themselves.
ALIASES = {
    "san francisco": "America/Los_Angeles", "seattle": "America/Los_Angeles", "silicon valley": "America/Los_Angeles",
    "san diego": "America/Los_Angeles", "portland": "America/Los_Angeles", "las vegas": "America/Los_Angeles",
    "california": "America/Los_Angeles", "washington": "America/New_York", "boston": "America/New_York",
    "miami": "America/New_York", "atlanta": "America/New_York", "philadelphia": "America/New_York",
    "austin": "America/Chicago", "dallas": "America/Chicago", "houston": "America/Chicago", "texas": "America/Chicago",
    "salt lake city": "America/Denver", "montreal": "America/Toronto", "ottawa": "America/Toronto",
    "hawaii": "Pacific/Honolulu", "rio": "America/Sao_Paulo", "rio de janeiro": "America/Sao_Paulo",
    "beijing": "Asia/Shanghai", "china": "Asia/Shanghai", "shenzhen": "Asia/Shanghai",
    "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata", "new delhi": "Asia/Kolkata", "bangalore": "Asia/Kolkata",
    "bengaluru": "Asia/Kolkata", "india": "Asia/Kolkata", "japan": "Asia/Tokyo", "osaka": "Asia/Tokyo",
    "korea": "Asia/Seoul", "vietnam": "Asia/Ho_Chi_Minh", "hanoi": "Asia/Bangkok", "bali": "Asia/Makassar",
    "abu dhabi": "Asia/Dubai", "tel aviv": "Asia/Jerusalem", "israel": "Asia/Jerusalem",
    "cape town": "Africa/Johannesburg", "south africa": "Africa/Johannesburg", "kyiv": "Europe/Kyiv",
    "kiev": "Europe/Kyiv", "rotterdam": "Europe/Amsterdam", "utrecht": "Europe/Amsterdam",
    "the hague": "Europe/Amsterdam", "den haag": "Europe/Amsterdam", "netherlands": "Europe/Amsterdam",
    "antwerp": "Europe/Brussels", "belgium": "Europe/Brussels", "munich": "Europe/Berlin",
    "hamburg": "Europe/Berlin", "frankfurt": "Europe/Berlin", "germany": "Europe/Berlin",
    "barcelona": "Europe/Madrid", "spain": "Europe/Madrid", "milan": "Europe/Rome", "italy": "Europe/Rome",
    "france": "Europe/Paris", "geneva": "Europe/Zurich", "switzerland": "Europe/Zurich",
    "edinburgh": "Europe/London", "manchester": "Europe/London", "uk": "Europe/London", "england": "Europe/London",
    "st petersburg": "Europe/Moscow", "wellington": "Pacific/Auckland", "new zealand": "Pacific/Auckland",
    "melbourne": "Australia/Melbourne", "canberra": "Australia/Sydney", "gmt": "UTC", "utc": "UTC",
}


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


_ZONES = None


def zones():
    global _ZONES
    if _ZONES is None:
        _ZONES = {}
        for z in available_timezones():
            if z.startswith(("Etc/", "SystemV/", "posix/", "right/")) or "/" not in z:
                continue
            city = z.rsplit("/", 1)[1].replace("_", " ").lower()
            _ZONES.setdefault(city, z)
            _ZONES[z.lower()] = z
    return _ZONES


def zone(place):
    """A place to (display name, zone key)."""
    key = " ".join(place.replace("_", " ").split()).lower().strip(" ,.")
    if not key:
        return None
    name = " ".join(w if w.isupper() else w.capitalize() for w in place.replace("_", " ").split())
    if key in ALIASES:
        return name, ALIASES[key]
    if key in zones():
        return name if "/" not in place else place.rsplit("/", 1)[1].replace("_", " "), zones()[key]
    if place in available_timezones():
        return place, place
    return None


def need_zone(place):
    z = zone(place)
    if not z:
        sys.exit(f"I do not know the time zone of {place}. Try a big city nearby or a zone like Europe/Paris.")
    return z


def places():
    out = []
    for p in values()["places"].split(","):
        z = zone(p.strip())
        if z and z not in out:
            out.append(z)
    return out


def local_zone():
    tz = os.environ.get("TZ")
    if tz and tz in available_timezones():
        return tz
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return None


def offset(dt):
    off = dt.utcoffset() or timedelta(0)
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    h, m = divmod(abs(minutes), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def day_note(dt, ref):
    diff = (dt.date() - ref.date()).days
    return {0: "", 1: ", tomorrow", -1: ", yesterday"}.get(diff, f", {dt.strftime('%a %d %b')}")


def parse_time(text):
    t = text.strip().lower().replace(".", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if not m:
        return None
    h, mi, half = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if half == "pm" and h < 12:
        h += 12
    if half == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return h, mi


# --- commands -------------------------------------------------------------------------------------

def cmd_now(args):
    here = datetime.now().astimezone()
    targets = [need_zone(" ".join(args))] if args else places()
    if not targets:
        print("No places yet. Keep one with: worldclock add <city>.")
        return
    for name, key in targets:
        t = datetime.now(ZoneInfo(key))
        diff = (t.utcoffset() - here.utcoffset()).total_seconds() / 3600
        rel = "same time as here" if diff == 0 else f"{abs(diff):g} h {'ahead' if diff > 0 else 'behind'}"
        print(f"{name}: {t.strftime('%H:%M')}{day_note(t, here)} ({offset(t)}, {rel})")


def cmd_at(args):
    words = list(args)
    source = None
    if "in" in [w.lower() for w in words]:
        i = [w.lower() for w in words].index("in")
        source = need_zone(" ".join(words[i + 1:]))
        words = words[:i]
    parsed = parse_time(" ".join(words))
    if not parsed:
        sys.exit("worldclock at <time> [in <place>], like: worldclock at 15:00 in Tokyo")
    src_key = source[1] if source else (local_zone() or "UTC")
    base = datetime.now(ZoneInfo(src_key)).replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0)
    print(f"{base.strftime('%H:%M')} {'in ' + source[0] if source else 'here'} is:")
    targets = [p for p in places() if p[1] != src_key]
    here_key = local_zone()
    if source and here_key and here_key != src_key and here_key not in [k for _, k in targets]:
        targets.insert(0, ("here", here_key))
    for name, key in targets:
        t = base.astimezone(ZoneInfo(key))
        print(f"  {name}: {t.strftime('%H:%M')}{day_note(t, base)}")
    if not targets:
        print(f"  UTC: {base.astimezone(ZoneInfo('UTC')).strftime('%H:%M')}")


def cmd_meet(args):
    targets = [need_zone(p.strip()) for p in " ".join(args).split(",") if p.strip()] if args else places()
    here = local_zone()
    if here and here not in [k for _, k in targets]:
        targets = [("here", here)] + targets
    if len(targets) < 2:
        sys.exit("Name at least two places, like: worldclock meet London, New York")
    today = datetime.now(ZoneInfo("UTC")).replace(minute=0, second=0, microsecond=0)
    good = []
    for h in range(24):
        slot = today.replace(hour=h)
        local = [slot.astimezone(ZoneInfo(k)) for _, k in targets]
        if all(WORK[0] <= t.hour < WORK[1] for t in local):
            good.append(local)
    if not good:
        print("There is no hour when it is between 9 and 17 everywhere. The closest:")
        best = min(range(24), key=lambda h: sum(
            max(0, WORK[0] - today.replace(hour=h).astimezone(ZoneInfo(k)).hour,
                today.replace(hour=h).astimezone(ZoneInfo(k)).hour - WORK[1] + 1) for _, k in targets))
        good = [[today.replace(hour=best).astimezone(ZoneInfo(k)) for _, k in targets]]
    else:
        print(f"Working hours overlap for {len(good)} hour{'s' if len(good) != 1 else ''}:")
    for local in good:
        print("  " + ", ".join(f"{name} {t.strftime('%H:%M')}" for (name, _), t in zip(targets, local)))


def cmd_add(args):
    place = " ".join(args).strip()
    if not place:
        sys.exit("worldclock add <place>")
    name, key = need_zone(place)
    current = [p.strip() for p in values()["places"].split(",") if p.strip()]
    if any(zone(p) and zone(p)[0].lower() == name.lower() for p in current):
        print(f"{name} is already there.")
        return
    keep("places", ", ".join(current + [name]))
    t = datetime.now(ZoneInfo(key))
    print(f"Keeping {name}, where it is {t.strftime('%H:%M')} now.")


def cmd_remove(args):
    place = " ".join(args).strip().lower()
    current = [p.strip() for p in values()["places"].split(",") if p.strip()]
    kept = [p for p in current if p.lower() != place]
    if len(kept) == len(current):
        sys.exit(f"{place} is not one of your places.")
    keep("places", ", ".join(kept))
    print(f"Dropped {place}.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] != "places":
        sys.exit("worldclock settings set places <city, city>")
    names = [p.strip() for p in " ".join(args[2:]).split(",") if p.strip()]
    unknown = [p for p in names if not zone(p)]
    if unknown:
        sys.exit(f"I do not know the time zone of {', '.join(unknown)}.")
    keep("places", ", ".join(names))
    print(f"Your places: {', '.join(names) or 'none'}.")


def main(argv):
    cmd, rest = (argv[0].lower(), argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_now([])
    elif cmd == "at":
        cmd_at(rest)
    elif cmd == "meet":
        cmd_meet(rest)
    elif cmd == "add":
        cmd_add(rest)
    elif cmd == "remove":
        cmd_remove(rest)
    elif cmd == "settings":
        cmd_settings(rest)
    elif parse_time(cmd):
        cmd_at(argv)
    else:
        cmd_now(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
