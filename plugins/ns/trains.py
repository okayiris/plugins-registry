#!/usr/bin/env python3
"""Dutch trains, live from the NS: departures, the best trips from A to B, and disruptions.

  trains                                departures from your home station
  trains <station>                      departures from a station
  trains to <station> [from <station>] [at HH:MM | arrive HH:MM]
                                        the next trips, from home unless you say otherwise
  trains home / trains work             the next trips to home or to work
  trains disruptions [station]          what is disrupted or has works now
  trains stations <text>                find a station and its code
  trains key / trains key ask           is there a key in the vault / paste one in
  trains settings                       the values as JSON
  trains settings set <key> <station>   change one value (home, work)

The NS key stays in the vault. Every call is made by the vault, which fills in the key as {g}; this
script never sees it. The key is free at apiportal.ns.nl: subscribe to Ns-App, the primary key.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
STATIONS_FILE = os.path.join(HERE, ".stations.json")
API = "https://gateway.apiportal.ns.nl/reisinformatie-api/api/"
ITEM = "ns"
DEFAULT = {"home": "", "work": ""}


def fail(msg):
    sys.exit(msg)


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


# --- the vault ------------------------------------------------------------------------------------

def vault_bin():
    p = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN")
    return p or shutil.which("kluis") or shutil.which("vault")


def key_item():
    exe = vault_bin()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    items = []
    for line in r.stdout.splitlines():
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p]
        if len(parts) >= 3 and not line.strip().startswith("de kluis"):
            items.append((parts[0], parts[2].strip().lower()))
    for name, _ in items:
        if name == ITEM:
            return name
    for name, domain in items:
        if domain.endswith("ns.nl"):
            return name
    return None


def call(path, **params):
    item = key_item()
    if not item:
        fail("There is no NS key in the vault yet. Say: trains key ask. "
             "It is free at apiportal.ns.nl: subscribe to Ns-App and use the primary key.")
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    cmd = [vault_bin(), "doe", item, "GET", url, "--kop", "Ocp-Apim-Subscription-Key: {g}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        fail("The NS did not answer in time.")
    first, _, rest = (r.stdout or "").partition("\n")
    m = re.match(r"status\s+(\d+)", first.strip())
    if not m:
        fail((r.stderr or r.stdout or "").strip() or "The vault refused the call.")
    status = int(m.group(1))
    if status in (401, 403):
        fail("The NS refused the key. Put a fresh one in the vault with: trains key ask.")
    if status == 429:
        fail("The NS asks to slow down. Try again in a minute.")
    if status >= 400:
        fail(f"The NS answered with status {status}.")
    try:
        return json.loads(rest)
    except ValueError:
        fail("The NS gave an answer I could not read.")


# --- stations -------------------------------------------------------------------------------------

def all_stations():
    try:
        with open(STATIONS_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - cached.get("at", 0) < 30 * 86400 and cached.get("stations"):
            return cached["stations"]
    except (OSError, ValueError):
        pass
    data = call("v2/stations")
    stations = []
    for s in data.get("payload") or []:
        names = s.get("namen") or {}
        stations.append({"code": s.get("code", ""), "name": names.get("lang") or names.get("middel") or s.get("code", ""),
                         "short": names.get("kort", ""), "country": s.get("land", ""),
                         "synonyms": s.get("synoniemen") or []})
    with open(STATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump({"at": time.time(), "stations": stations}, f)
    return stations


def find_stations(text):
    t = text.strip().lower()
    stations = all_stations()
    exact = [s for s in stations if t in (s["code"].lower(), s["name"].lower(), s["short"].lower())
             or t in [x.lower() for x in s["synonyms"]]]
    if exact:
        return exact
    # "Utrecht" means Utrecht Centraal before Utrecht Overvecht; Dutch stations first.
    hits = [s for s in stations if s["name"].lower().startswith(t)] or [s for s in stations if t in s["name"].lower()]
    hits.sort(key=lambda s: (s["country"] != "NL", "centraal" not in s["name"].lower(), len(s["name"])))
    return hits


def station(text):
    hits = find_stations(text)
    if not hits:
        fail(f"There is no station called {text}.")
    return hits[0]


def home_station(key="home"):
    value = values()[key]
    if not value:
        fail(f"No {key} station is set. Say: trains settings set {key} <station>.")
    return station(value)


# --- showing --------------------------------------------------------------------------------------

def parse_time(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def clock(planned, actual):
    p, a = parse_time(planned), parse_time(actual)
    if not p:
        return "?"
    text = p.strftime("%H:%M")
    if a:
        late = round((a - p).total_seconds() / 60)
        if late > 0:
            text += f" +{late}"
    return text


def track(stop):
    planned, actual = stop.get("plannedTrack"), stop.get("actualTrack")
    if actual and planned and actual != planned:
        return f"track {actual} (not {planned})"
    return f"track {actual or planned}" if (actual or planned) else ""


# --- commands -------------------------------------------------------------------------------------

def cmd_departures(args):
    st = station(" ".join(args)) if args else home_station()
    data = call("v2/departures", station=st["code"], maxJourneys=12)
    deps = (data.get("payload") or {}).get("departures") or []
    if not deps:
        print(f"No departures from {st['name']} right now.")
        return
    print(f"Departures from {st['name']}:")
    for d in deps[:10]:
        kind = (d.get("product") or {}).get("shortCategoryName") or d.get("trainCategory", "")
        where = track({"plannedTrack": d.get("plannedTrack"), "actualTrack": d.get("actualTrack")})
        line = f"  {clock(d.get('plannedDateTime'), d.get('actualDateTime'))}  {kind} {d.get('direction', '?')}"
        if d.get("cancelled"):
            line += "  CANCELLED"
        elif where:
            line += f"  {where}"
        print(line)
        for msg in d.get("messages") or []:
            if msg.get("style") in ("WARNING", "ERROR") and msg.get("message"):
                print(f"         {msg['message']}")


def cmd_trip(args):
    words = list(args)
    lower = [w.lower() for w in words]
    at, arrive = None, False
    for flag in ("at", "arrive"):
        if flag in lower:
            i = lower.index(flag)
            if i + 1 < len(words) and re.fullmatch(r"\d{1,2}[:.]\d{2}", words[i + 1]):
                at, arrive = words[i + 1].replace(".", ":"), flag == "arrive"
                del words[i:i + 2]
                lower = [w.lower() for w in words]
    origin = None
    if "from" in lower:
        i = lower.index("from")
        origin = station(" ".join(words[i + 1:]))
        words = words[:i]
    if not words:
        fail("trains to <station> [from <station>] [at HH:MM | arrive HH:MM]")
    dest = station(" ".join(words))
    origin = origin or home_station()
    if origin["code"] == dest["code"]:
        fail(f"You are already at {dest['name']}.")
    params = {"fromStation": origin["code"], "toStation": dest["code"]}
    if at:
        h, m = map(int, at.split(":"))
        when = datetime.now(ZoneInfo("Europe/Amsterdam")).replace(hour=h, minute=m, second=0, microsecond=0)
        params["dateTime"] = when.isoformat(timespec="seconds")
        if arrive:
            params["searchForArrival"] = "true"
    data = call("v3/trips", **params)
    trips = [t for t in data.get("trips") or [] if t.get("legs")]
    if not trips:
        print(f"No trips found from {origin['name']} to {dest['name']}.")
        return
    print(f"{origin['name']} to {dest['name']}:")
    for t in trips[:4]:
        first, last = t["legs"][0]["origin"], t["legs"][-1]["destination"]
        minutes = t.get("actualDurationInMinutes") or t.get("plannedDurationInMinutes")
        changes = t.get("transfers", len(t["legs"]) - 1)
        line = (f"  {clock(first.get('plannedDateTime'), first.get('actualDateTime'))} to "
                f"{clock(last.get('plannedDateTime'), last.get('actualDateTime'))}, {minutes} min, "
                + ("direct" if not changes else f"{changes} change{'s' if changes != 1 else ''}"))
        where = track(first)
        if where:
            line += f", {where}"
        status = t.get("status", "NORMAL")
        if status == "CANCELLED" or any(l.get("cancelled") for l in t["legs"]):
            line += "  CANCELLED"
        elif status not in ("NORMAL", ""):
            line += f"  ({status.lower().replace('_', ' ')})"
        print(line)
        if changes:
            via = [f"{l['destination'].get('name')} {track(l['destination'])}".strip() for l in t["legs"][:-1]]
            print(f"      change at {', '.join(via)}")


def cmd_disruptions(args):
    data = call("v3/disruptions", isActive="true")
    items = data if isinstance(data, list) else data.get("payload") or []
    if args:
        hits = find_stations(" ".join(args))
        # The whole name as a phrase: "Den Haag" finds Den Haag Centraal and Den Haag HS, not Leiden.
        asked = " ".join(args).strip().lower()
        names = {asked} | ({hits[0]["name"].lower()} if hits else set())
        pattern = re.compile("|".join(r"\b" + re.escape(n) + r"\b" for n in names))
        items = [d for d in items if pattern.search(json.dumps(d, ensure_ascii=False).lower())]
    if not items:
        print("No disruptions or works right now" + (f" around {' '.join(args)}." if args else "."))
        return
    kinds = {"CALAMITY": "calamity", "DISRUPTION": "disruption", "MAINTENANCE": "works"}
    print(f"{len(items)} now:")
    for d in items[:12]:
        label = ""
        for span in d.get("timespans") or []:
            label = (span.get("situation") or {}).get("label") or ""
            if label:
                break
        kind = kinds.get(d.get("type", ""), d.get("type", "").lower())
        print(f"  {kind}: {d.get('title', '?')}" + (f". {label}" if label else ""))


def cmd_stations(args):
    text = " ".join(args).strip()
    if not text:
        fail("trains stations <text>")
    hits = find_stations(text)[:8]
    if not hits:
        print(f"No station called {text}.")
        return
    for s in hits:
        print(f"  {s['name']} ({s['code']})" + (f", {s['country']}" if s["country"] and s["country"] != "NL" else ""))


def cmd_key(args):
    if args and args[0] == "ask":
        exe = vault_bin()
        if not exe:
            fail("The vault is not on this system.")
        print("A window opens to paste your NS API key; it goes straight into the vault.")
        r = subprocess.run([exe, "vraag", ITEM, "--domein", "gateway.apiportal.ns.nl", "NS API key (Ns-App, primary key)"],
                           capture_output=True, text=True, timeout=240)
        if r.returncode != 0:
            fail((r.stderr or r.stdout).strip() or "The vault did not save a key.")
        print((r.stdout or "").strip() or "Saved in the vault.")
        return
    item = key_item()
    print(f'An NS key is in the vault as "{item}".' if item else "No NS key in the vault yet. Say: trains key ask.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in ("home", "work"):
        fail("trains settings set <home|work> <station>")
    text = " ".join(args[2:]).strip()
    if not text:
        keep(args[1], "")
        print(f"No {args[1]} station any more.")
        return
    st = station(text)
    keep(args[1], st["name"])
    print(f"Your {args[1]} station is {st['name']}.")


def cmd_commute(where):
    """To work from home, or home from work."""
    other = "work" if where == "home" else "home"
    if not values()[where]:
        fail(f"No {where} station is set. Say: trains settings set {where} <station>.")
    if not values()[other]:
        fail(f"From where? Say: trains to {values()[where]} from <station>, or set your {other} station.")
    cmd_trip([values()[where], "from", values()[other]])


def main(argv):
    cmd, rest = (argv[0].lower(), argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_departures([])
    elif cmd == "to":
        cmd_trip(rest)
    elif cmd in ("home", "work") and not rest:
        cmd_commute(cmd)
    elif cmd == "disruptions":
        cmd_disruptions(rest)
    elif cmd == "stations":
        cmd_stations(rest)
    elif cmd == "key" and len(rest) <= 1:
        cmd_key(rest)
    elif cmd == "settings":
        cmd_settings(rest)
    else:
        cmd_departures(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
