#!/usr/bin/env python3
"""The sun and the moon where you are: sunrise, sunset, daylight, twilight, golden hour, and the moon's phase.

  sun                                   today at home: sunrise, sunset, how long the day is, twilight
  sun <place>                           the same somewhere else
  sun on <date> [place]                 another day, like: sun on 2026-12-21, sun on 21 Dec
  sun moon                              the moon now, and its next phases
  sun settings                          the values as JSON
  sun settings set place <place>        home, looked up once (or given as 52.09,5.12)

Everything is calculated here, offline, with the NOAA sun formula and Meeus' moon phases: to within a
minute or two for the sun and a few minutes for the moon. Only looking up a place name asks the internet.
"""
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
DEFAULT = {"place": ""}
SYNODIC = 29.530588861
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def values():
    out = dict(DEFAULT)
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            kept = json.load(f)
        if isinstance(kept, dict):
            out.update(kept)
    except (OSError, ValueError):
        pass
    return out


def save(data):
    with open(VALUES_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def geocode(name):
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", name)
    if m:
        return {"label": f"{float(m.group(1)):.2f}, {float(m.group(2)):.2f}", "lat": float(m.group(1)), "lon": float(m.group(2))}
    req = urllib.request.Request(GEOCODE + "?" + urllib.parse.urlencode({"name": name, "count": 1, "format": "json"}),
                                 headers={"User-Agent": "Iris-sun/1.0"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                results = json.loads(resp.read().decode()).get("results") or []
            break
        except (OSError, ValueError, urllib.error.URLError):
            if attempt == 2:
                sys.exit("Looking up the place did not work. Give it as coordinates, like 52.09,5.12.")
    if not results:
        return None
    r = results[0]
    parts = []
    for x in (r.get("name"), r.get("admin1"), r.get("country")):
        if x and x not in parts:
            parts.append(x)
    return {"label": ", ".join(parts), "lat": r["latitude"], "lon": r["longitude"]}


def home():
    v = values()
    if v.get("lat") is None:
        sys.exit("No home is set yet. Say where you live: sun settings set place <city>.")
    return {"label": v.get("label") or v.get("place"), "lat": v["lat"], "lon": v["lon"]}


# --- the sun (NOAA / the sunrise equation) -------------------------------------------------------

def rad(d):
    return math.radians(d)


def sun_times(day, lat, lon):
    """Moments (UTC datetimes) when the sun's centre is at a set of altitudes, for one date."""
    jd_noon = day.toordinal() + 1721424.5 + 0.5          # Julian day at 12:00 UTC
    n = round(jd_noon - 2451545.0 + 0.0008)
    j_star = n - lon / 360.0
    m = (357.5291 + 0.98560028 * j_star) % 360
    c = 1.9148 * math.sin(rad(m)) + 0.0200 * math.sin(rad(2 * m)) + 0.0003 * math.sin(rad(3 * m))
    lam = (m + c + 180 + 102.9372) % 360
    transit = 2451545.0 + j_star + 0.0053 * math.sin(rad(m)) - 0.0069 * math.sin(rad(2 * lam))
    dec = math.asin(math.sin(rad(lam)) * math.sin(rad(23.4397)))

    def to_dt(jd):
        return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - 2451545.0)

    def around(alt):
        cos_w = (math.sin(rad(alt)) - math.sin(rad(lat)) * math.sin(dec)) / (math.cos(rad(lat)) * math.cos(dec))
        if cos_w > 1:
            return "below"      # the sun stays below this altitude all day
        if cos_w < -1:
            return "above"      # the sun stays above it all day
        w = math.degrees(math.acos(cos_w))
        return to_dt(transit - w / 360), to_dt(transit + w / 360)

    return {"noon": to_dt(transit), "rise": around(-0.833), "civil": around(-6.0), "golden": around(6.0)}


def local(dt):
    return dt.astimezone().strftime("%H:%M")


def day_length(times):
    rs = times["rise"]
    if rs == "below":
        return timedelta(0)
    if rs == "above":
        return timedelta(days=1)
    return rs[1] - rs[0]


def span(td):
    minutes = round(td.total_seconds() / 60)
    h, m = divmod(abs(minutes), 60)
    return f"{h} h {m} min" if h else f"{m} min"


# --- the moon (Meeus, Astronomical Algorithms, chapters 48 and 49) -------------------------------

def phase_jde(k, kind):
    """The moment of a phase (Julian Ephemeris Day). kind: 0 new, 1 first quarter, 2 full, 3 last quarter."""
    k = k + kind / 4
    t = k / 1236.85
    jde = (2451550.09766 + SYNODIC * k + 0.00015437 * t ** 2 - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4)
    e = 1 - 0.002516 * t - 0.0000074 * t ** 2
    m = rad(2.5534 + 29.10535670 * k - 0.0000014 * t ** 2 - 0.00000011 * t ** 3)
    mp = rad(201.5643 + 385.81693528 * k + 0.0107582 * t ** 2 + 0.00001238 * t ** 3 - 0.000000058 * t ** 4)
    f = rad(160.7108 + 390.67050284 * k - 0.0016118 * t ** 2 - 0.00000227 * t ** 3 + 0.000000011 * t ** 4)
    om = rad(124.7746 - 1.56375588 * k + 0.0020672 * t ** 2 + 0.00000215 * t ** 3)
    s = math.sin
    if kind in (0, 2):
        a = (-0.40720, 0.17241, 0.01608, 0.01039, 0.00739, -0.00514, 0.00208) if kind == 0 else \
            (-0.40614, 0.17302, 0.01614, 0.01043, 0.00734, -0.00515, 0.00209)
        jde += (a[0] * s(mp) + a[1] * e * s(m) + a[2] * s(2 * mp) + a[3] * s(2 * f) + a[4] * e * s(mp - m)
                + a[5] * e * s(mp + m) + a[6] * e * e * s(2 * m) - 0.00111 * s(mp - 2 * f) - 0.00057 * s(mp + 2 * f)
                + 0.00056 * e * s(2 * mp + m) - 0.00042 * s(3 * mp) + 0.00042 * e * s(m + 2 * f)
                + 0.00038 * e * s(m - 2 * f) - 0.00024 * e * s(2 * mp - m) - 0.00017 * s(om))
    else:
        jde += (-0.62801 * s(mp) + 0.17172 * e * s(m) - 0.01183 * e * s(mp + m) + 0.00862 * s(2 * mp)
                + 0.00804 * s(2 * f) + 0.00454 * e * s(mp - m) + 0.00204 * e * e * s(2 * m) - 0.00180 * s(mp - 2 * f)
                - 0.00070 * s(mp + 2 * f) - 0.00040 * s(3 * mp) - 0.00034 * e * s(2 * mp - m)
                + 0.00032 * e * s(m + 2 * f) + 0.00032 * e * s(m - 2 * f) - 0.00028 * e * e * s(mp + 2 * m)
                + 0.00027 * e * s(2 * mp + m) - 0.00017 * s(om))
        w = (0.00306 - 0.00038 * e * math.cos(m) + 0.00026 * math.cos(mp) - 0.00002 * math.cos(mp - m)
             + 0.00002 * math.cos(mp + m) + 0.00002 * math.cos(2 * f))
        jde += w if kind == 1 else -w
    return jde


def jde_to_utc(jde):
    return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jde - 2451545.0, seconds=-69)  # TT to UT


def phases_after(moment, count=4):
    """The next `count` phases after a moment, as (name, utc datetime)."""
    names = ["New moon", "First quarter", "Full moon", "Last quarter"]
    years = moment.year + (moment.timetuple().tm_yday - 1) / 365.25
    k = math.floor((years - 2000) * 12.3685) - 1
    out = []
    while len(out) < count:
        for kind in range(4):
            at = jde_to_utc(phase_jde(k, kind))
            if at > moment:
                out.append((names[kind], at))
        k += 1
    return sorted(out, key=lambda x: x[1])[:count]


def moon_now(moment):
    """How much of the moon is lit, and whether it is waxing (Meeus 48, the simple way)."""
    jd = moment.timestamp() / 86400 + 2440587.5
    t = (jd - 2451545.0) / 36525
    d = rad(297.8501921 + 445267.1114034 * t)
    m = rad(357.5291092 + 35999.0502909 * t)
    mp = rad(134.9633964 + 477198.8675055 * t)
    i = (180 - math.degrees(d) - 6.289 * math.sin(mp) + 2.100 * math.sin(m) - 1.274 * math.sin(2 * d - mp)
         - 0.658 * math.sin(2 * d) - 0.214 * math.sin(2 * mp) - 0.110 * math.sin(d))
    lit = (1 + math.cos(rad(i))) / 2
    waxing = (math.degrees(d) % 360) < 180   # the moon is east of the sun: growing
    return lit, waxing


def moon_name(lit, waxing):
    if lit < 0.03:
        return "new moon"
    if lit > 0.97:
        return "full moon"
    if 0.45 <= lit <= 0.55:
        return "first quarter" if waxing else "last quarter"
    if lit < 0.5:
        return "waxing crescent" if waxing else "waning crescent"
    return "waxing gibbous" if waxing else "waning gibbous"


# --- commands -------------------------------------------------------------------------------------

def parse_day(text):
    t = text.strip().lower()
    if t in ("today", ""):
        return date.today()
    if t == "tomorrow":
        return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(t)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})\s+([a-z]+)\s*(\d{4})?", t) or re.fullmatch(r"([a-z]+)\s+(\d{1,2}),?\s*(\d{4})?", t)
    if m:
        a, b, y = m.groups()
        dd, mon = (int(a), b) if a.isdigit() else (int(b), a)
        if mon[:3] in MONTHS:
            try:
                return date(int(y) if y else date.today().year, MONTHS[mon[:3]], dd)
            except ValueError:
                return None
    return None


def cmd_sun(day, where):
    times = sun_times(day, where["lat"], where["lon"])
    label = "today" if day == date.today() else day.strftime("%a %d %b %Y")
    rise = times["rise"]
    if rise == "below":
        print(f"{where['label']}, {label}: the sun does not rise (polar night).")
        return
    if rise == "above":
        print(f"{where['label']}, {label}: the sun does not set (midnight sun).")
        return
    length = day_length(times)
    before = day_length(sun_times(day - timedelta(days=1), where["lat"], where["lon"]))
    diff = round((length - before).total_seconds() / 60)
    change = "" if diff == 0 else f" ({abs(diff)} min {'more' if diff > 0 else 'less'} than the day before)"
    print(f"{where['label']}, {label}: sunrise {local(rise[0])}, sunset {local(rise[1])}, "
          f"{span(length)} of daylight{change}.")
    civil = times["civil"]
    if isinstance(civil, tuple):
        print(f"Light from {local(civil[0])} until {local(civil[1])} (civil twilight); the sun is highest at {local(times['noon'])}.")
    golden = times["golden"]
    if isinstance(golden, tuple):
        print(f"Golden hour: until {local(golden[0])} in the morning and from {local(golden[1])} in the evening.")
    elif golden == "below":
        print("Golden light all day: the sun stays low.")


def cmd_moon():
    moment = datetime.now(timezone.utc)
    lit, waxing = moon_now(moment)
    print(f"The moon now: {moon_name(lit, waxing)}, {round(lit * 100)}% lit.")
    for name, at in phases_after(moment):
        loc = at.astimezone()
        days = (loc.date() - date.today()).days
        when = {0: "today", 1: "tomorrow"}.get(days) or loc.strftime("%a %d %b")
        print(f"  {name}: {when} around {loc.strftime('%H:%M')}")


def cmd_settings(args):
    v = values()
    if not args:
        print(json.dumps({"place": v.get("place", "")}, ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] != "place":
        sys.exit("sun settings set place <place>")
    text = " ".join(args[2:]).strip()
    if not text:
        save({"place": ""})
        print("Home is cleared.")
        return
    where = geocode(text)
    if not where:
        sys.exit(f"I could not find a place called {text}.")
    save({"place": text, **where})
    print(f"Home is {where['label']}.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_sun(date.today(), home())
    elif cmd == "moon":
        cmd_moon()
    elif cmd == "settings":
        cmd_settings(rest)
    elif cmd == "on":
        # "sun on 21 Dec Lisbon": the date is the longest start that reads as one, the rest is a place.
        for n in (3, 2, 1):
            day = parse_day(" ".join(rest[:n])) if len(rest) >= n else None
            if day:
                place = " ".join(rest[n:]).strip()
                break
        else:
            sys.exit("sun on <date> [place], like: sun on 2026-12-21 or sun on 21 Dec")
        where = geocode(place) if place else home()
        if not where:
            sys.exit(f"I could not find a place called {place}.")
        cmd_sun(day, where)
    else:
        where = geocode(" ".join(argv))
        if not where:
            sys.exit(f"I could not find a place called {' '.join(argv)}.")
        cmd_sun(date.today(), where)


if __name__ == "__main__":
    main(sys.argv[1:])
