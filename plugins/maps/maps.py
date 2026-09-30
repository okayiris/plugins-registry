#!/usr/bin/env python3
"""Maps for Iris: routes, travel time and places through your own Google Maps API key.

  maps                          what is set up, and what is still missing
  maps key ask                  ask for your Google Maps API key (it goes straight into the vault)
  maps key                      which vault item is used, never the key itself
  maps home "<address>"         remember your home address (not a secret)
  maps route "<to>"             route from home, with travel time and live traffic when available
  maps route "<from>" "<to>"    route between two addresses or places
  maps find "<query>" [--near "<place>"] [-n 5]
                                find places, with address, rating and whether they are open
  maps geocode "<address>"      coordinates and the formatted address

Flags for route: --mode driving|walking|bicycling|transit (default driving).
Add --json to route or find for the answer as data, for another plugin (like planassistant).

Your key stays in the vault. The vault makes the call with the key filled in as {g}, so this
tool never sees it and it never ends up in a log or a file. Enable the Geocoding API, the
Directions API and the Places API on the key. Set up with: maps key ask
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG = os.path.join(HERE, "config.json")

GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
DIRECTIONS = "https://maps.googleapis.com/maps/api/directions/json"
PLACES = "https://maps.googleapis.com/maps/api/place/textsearch/json"

VAULT_ITEM = "maps"
VAULT_DOMAIN = "maps.googleapis.com"
MODES = ("driving", "walking", "bicycling", "transit")
AS_JSON = "--json" in sys.argv[1:]


def fail(text):
    print(json.dumps({"error": text}) if AS_JSON else f"maps: {text}")
    sys.exit(1)


# ---------------------------------------------------------------- vault

def vault_bin():
    p = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN")
    if p:
        return p
    return shutil.which("kluis") or shutil.which("vault")


def vault_items():
    exe = vault_bin()
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    items = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        parts = [p for p in re.split(r"\s{2,}", line) if p]
        if len(parts) >= 3:
            items.append({"name": parts[0], "user": parts[1], "domain": parts[2]})
    return items


def key_item():
    items = vault_items()
    for it in items:
        if it["name"] == VAULT_ITEM:
            return it["name"]
    for it in items:
        if it["domain"].strip().lower() == VAULT_DOMAIN:
            return it["name"]
    return None


def cmd_key(args):
    if args and args[0] == "ask":
        exe = vault_bin()
        if not exe:
            fail("the vault command (kluis) is not on this system.")
        print("A window opens to paste your Google Maps API key; it goes straight into the vault.")
        try:
            r = subprocess.run(
                [exe, "vraag", VAULT_ITEM, "--domein", VAULT_DOMAIN,
                 "Google Maps API key (enable Geocoding, Directions and Places API on it)"],
                capture_output=True, text=True, timeout=220)
        except subprocess.TimeoutExpired:
            fail("the vault did not answer in time.")
        out = (r.stdout or "").strip()
        if r.returncode != 0:
            fail((r.stderr or "").strip() or out or "the vault did not save a key.")
        print(out or f'saved in the vault as "{VAULT_ITEM}".')
        return
    item = key_item()
    if not item:
        print("No Google Maps API key in the vault yet. Run: maps key ask")
        return
    print(f'Using the vault item "{item}" for {VAULT_DOMAIN}. The key itself is never shown.')


def vault_call(item, method, url, headers=None, body=None, timeout=60):
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system.")
    cmd = [exe, "doe", item, method, url]
    if body is not None:
        cmd.append(body)
    for h in headers or []:
        cmd += ["--kop", h]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        fail("the vault did not answer in time.")
    except OSError as exc:
        fail(str(exc))
    out = r.stdout or ""
    if not out.strip():
        fail((r.stderr or "").strip() or "no answer from the vault.")
    first, _, rest = out.partition("\n")
    status = 0
    m = re.match(r"status\s+(\d+)", first.strip())
    if m:
        status = int(m.group(1))
    return status, rest


# ---------------------------------------------------------------- http

def enc(params):
    parts = []
    for k, v in params:
        if v is None:
            continue
        if v == "{g}":
            parts.append(f"{k}={{g}}")
        else:
            parts.append(f"{k}={urllib.parse.quote(str(v))}")
    return "&".join(parts)


def google(url, params):
    item = key_item()
    if not item:
        fail('no Google Maps API key in the vault yet. Run `maps key ask` first.')
    status, text = vault_call(item, "GET", url + "?" + enc(params))
    try:
        data = json.loads(text)
    except ValueError:
        fail(f"Google returned an unreadable answer (status {status}).")
    gstatus = data.get("status")
    if gstatus and gstatus not in ("OK", "ZERO_RESULTS"):
        fail(f"Google: {data.get('error_message') or gstatus}")
    return data


# ---------------------------------------------------------------- config

def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(d):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
        f.write("\n")
    os.replace(tmp, CONFIG)


def resolve(text):
    if text.strip().lower() in ("home", "thuis"):
        home = str(load_config().get("home") or "").strip()
        if not home:
            fail('no home address yet. Set it with: maps home "<address>"')
        return home
    return text


def cmd_home(args):
    if not args:
        home = str(load_config().get("home") or "").strip()
        print(f"Home: {home}" if home else 'No home address yet. Set it with: maps home "<address>"')
        return
    address = " ".join(args).strip()
    cfg = load_config()
    cfg["home"] = address
    save_config(cfg)
    print(f"Home set to: {address}")


# ---------------------------------------------------------------- commands

def fmt_distance(meters):
    if meters is None:
        return "?"
    if meters < 1000:
        return f"{round(meters)} m"
    return f"{meters / 1000:.1f} km"


def fmt_duration(seconds):
    if seconds is None:
        return "?"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def cmd_route(args):
    mode = "driving"
    free = []
    i = 0
    while i < len(args):
        if args[i] == "--mode":
            if i + 1 >= len(args):
                fail("--mode needs a value: driving, walking, bicycling or transit")
            mode = args[i + 1].lower()
            i += 2
            continue
        if args[i].startswith("--"):
            i += 1
            continue
        free.append(args[i])
        i += 1
    if mode not in MODES:
        fail(f"unknown mode {mode!r}; use one of {', '.join(MODES)}.")
    if not free:
        fail('use: maps route "<to>" or maps route "<from>" "<to>"')
    if len(free) == 1:
        start = resolve("home")
        end = free[0]
    else:
        start = resolve(free[0])
        end = resolve(free[1])

    params = [
        ("origin", start),
        ("destination", end),
        ("mode", mode),
        ("language", "en"),
        ("key", "{g}"),
    ]
    if mode in ("driving", "transit"):
        params.insert(3, ("departure_time", "now"))
    data = google(DIRECTIONS, params)
    routes = data.get("routes") or []
    if not routes:
        fail("no route found between those places.")
    leg = (routes[0].get("legs") or [{}])[0]
    duration = (leg.get("duration") or {}).get("value")
    traffic = (leg.get("duration_in_traffic") or {}).get("value")
    distance = (leg.get("distance") or {}).get("value")
    if AS_JSON:
        print(json.dumps({"from": leg.get("start_address", start), "to": leg.get("end_address", end), "mode": mode,
                          "meters": distance, "seconds": duration, "traffic_seconds": traffic}, ensure_ascii=False))
        return

    print(f"Route ({mode}): {leg.get('start_address', start)} -> {leg.get('end_address', end)}")
    line = f"  {fmt_duration(duration)}, {fmt_distance(distance)}"
    if traffic and traffic > (duration or 0) + 60:
        line += f" (with traffic {fmt_duration(traffic)})"
    print(line)
    print(f"  {routes[0].get('summary', '')}".rstrip())


def cmd_geocode(args):
    if not args:
        fail('use: maps geocode "<address>"')
    address = " ".join(args).strip()
    data = google(GEOCODE, [("address", address), ("language", "en"), ("key", "{g}")])
    results = data.get("results") or []
    if not results:
        print(f'No coordinates found for "{address}".')
        return
    top = results[0]
    loc = (top.get("geometry") or {}).get("location") or {}
    print(f"{top.get('formatted_address', address)}")
    print(f"  {loc.get('lat')}, {loc.get('lng')}")


def cmd_find(args):
    n = 5
    near = None
    free = []
    i = 0
    while i < len(args):
        if args[i] in ("-n", "--n") and i + 1 < len(args):
            try:
                n = max(1, min(20, int(args[i + 1])))
            except ValueError:
                fail("-n needs a number")
            i += 2
            continue
        if args[i] == "--near" and i + 1 < len(args):
            near = args[i + 1]
            i += 2
            continue
        free.append(args[i])
        i += 1
    query = " ".join(free).strip()
    if not query:
        fail('use: maps find "<query>" [--near "<place>"] [-n 5]')
    if near:
        query = f"{query} near {near}"
    data = google(PLACES, [("query", query), ("language", "en"), ("key", "{g}")])
    results = data.get("results") or []
    if AS_JSON:
        print(json.dumps({"query": query, "places": [
            {"name": r.get("name", ""), "address": r.get("formatted_address") or r.get("vicinity", ""),
             "rating": r.get("rating"), "ratings": r.get("user_ratings_total"),
             "open_now": (r.get("opening_hours") or {}).get("open_now")} for r in results[:n]]}, ensure_ascii=False))
        return
    if not results:
        print(f'No places found for "{query}".')
        return
    for r in results[:n]:
        open_now = (r.get("opening_hours") or {}).get("open_now")
        extra = ""
        if r.get("rating"):
            extra += f", {r['rating']}/5"
            if r.get("user_ratings_total"):
                extra += f" ({r['user_ratings_total']})"
        if open_now is True:
            extra += ", open now"
        elif open_now is False:
            extra += ", closed now"
        print(f"{r.get('name', '?')}{extra}")
        print(f"  {r.get('formatted_address') or r.get('vicinity', '')}".rstrip())


def status():
    print("Maps: routes, travel time and places through your own Google Maps API key.")
    print()
    cfg = load_config()
    home = str(cfg.get("home") or "").strip()
    print(f"Home: {home}" if home else 'Home: not set (maps home "<address>")')
    item = key_item()
    if not item:
        print()
        print("No key yet. You need:")
        print("  1. a Google Cloud project with billing enabled")
        print("  2. an API key in APIs & Services > Credentials")
        print("  3. the Geocoding API, Directions API and Places API enabled for that project")
        print()
        print("Then run: maps key ask")
        return
    print(f'Key: vault item "{item}". The key itself is never read or shown.')
    print()
    print("Try: maps route \"<address>\"  |  maps find \"<query>\"  |  maps geocode \"<address>\"")


def main():
    a = [x for x in sys.argv[1:] if x != "--json"]
    if not a or a[0] in ("help", "--help", "-h"):
        if a:
            print(__doc__)
        else:
            status()
        return
    cmd = a[0]
    if cmd == "key":
        cmd_key(a[1:])
    elif cmd == "home":
        cmd_home(a[1:])
    elif cmd == "route":
        cmd_route(a[1:])
    elif cmd == "find":
        cmd_find(a[1:])
    elif cmd == "geocode":
        cmd_geocode(a[1:])
    else:
        status()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nmaps: stopped")
        sys.exit(1)
