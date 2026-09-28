#!/usr/bin/env python3
"""Travel time for Iris: how far and how long from home to an address.

  travel                              show the home address and which route service is used
  travel huis "<address>"             set the home address (looked up once)
  travel naar "<address>"             distance and travel time from home
  travel naar "<address>" --om 14:30  also say when to leave to arrive at 14:30

Your home address is not secret and lives in config.json next to this file:

  {"home": {"address": "...", "lat": 53.1, "lon": 6.3}}

Routes are free and need no key: OSRM (https://router.project-osrm.org) gives distance and duration,
without live traffic. Want live traffic? Ask a TomTom key and the plugin uses that instead:

  kluis vraag reistijd --domein api.tomtom.com "TomTom Routing API key"

The key never reaches this script: the call is made by the vault, with the key as {g} in the URL.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS = HERE / "config.json"
VAULT = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN") or "kluis"
PHOTON = "https://photon.komoot.io/api/"
OSRM = "https://router.project-osrm.org/route/v1/driving/"
TOMTOM = "https://api.tomtom.com/routing/1/calculateRoute/"


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(data):
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def home_of(settings):
    home = settings.get("home") or {}
    if home.get("lat") is not None and home.get("lon") is not None:
        return home
    return None


def http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Iris-reistijd/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"de dienst antwoordde met status {exc.code}"
    except (OSError, ValueError) as exc:
        return None, f"geen antwoord ({exc})"


def geocode(address):
    url = PHOTON + "?" + urllib.parse.urlencode({"q": address, "limit": 1})
    data, err = http_json(url)
    if err:
        return None, err
    features = data.get("features") or []
    if not features:
        return None, None
    feature = features[0]
    lon, lat = feature["geometry"]["coordinates"][:2]
    props = feature.get("properties") or {}
    parts = [props.get("name"), props.get("street"), props.get("housenumber"),
             props.get("postcode"), props.get("city"), props.get("country")]
    label = ", ".join(str(p) for p in parts if p)
    return {"lat": lat, "lon": lon, "label": label or address}, None


def vault_items():
    try:
        proc = subprocess.run([VAULT, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    items = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        parts = [p for p in re.split(r"\s{2,}", line) if p]
        if len(parts) >= 3:
            items.append({"name": parts[0], "user": parts[1], "domain": parts[2]})
    return items


def norm_domain(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    return value.split("/")[0].split(":")[0]


def tomtom_item():
    for item in vault_items():
        if norm_domain(item["domain"]) == "api.tomtom.com":
            return item["name"]
    return None


def vault_call(item, method, url, timeout=60):
    cmd = [VAULT, "doe", item, method, url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, "de kluis is niet gevonden"
    except subprocess.TimeoutExpired:
        return None, "de kluis antwoordde niet op tijd"
    except OSError as exc:
        return None, str(exc)
    if not proc.stdout.strip():
        return None, (proc.stderr.strip() or "geen antwoord van de kluis")
    first, _, rest = proc.stdout.partition("\n")
    status = None
    if first.startswith("status "):
        try:
            status = int(first.split()[1])
        except (IndexError, ValueError):
            pass
    return status, rest


def route_osrm(start, end):
    coords = f"{start['lon']},{start['lat']};{end['lon']},{end['lat']}"
    url = OSRM + coords + "?overview=false"
    data, err = http_json(url)
    if err:
        return None, err
    routes = data.get("routes") or []
    if data.get("code") != "Ok" or not routes:
        return None, "geen route gevonden"
    route = routes[0]
    return {"meters": route["distance"], "seconds": route["duration"], "traffic": False}, None


def route_tomtom(item, start, end, depart_at=None):
    coords = f"{start['lat']},{start['lon']}:{end['lat']},{end['lon']}"
    params = {"key": "{g}", "traffic": "true", "travelMode": "car"}
    if depart_at:
        params["departAt"] = depart_at.strftime("%Y-%m-%dT%H:%M:%S")
    url = TOMTOM + coords + "/json?" + "&".join(
        f"{k}={{g}}" if v == "{g}" else f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    status, text = vault_call(item, "GET", url)
    if status is None:
        return None, text
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None, "TomTom gaf geen leesbaar antwoord."
    if status == 401 or status == 403:
        return None, "TomTom weigerde de sleutel."
    if status >= 400:
        return None, f"TomTom antwoordde met status {status}."
    routes = data.get("routes") or []
    if not routes:
        return None, "geen route gevonden"
    summary = routes[0].get("summary") or {}
    seconds = summary.get("travelTimeInSeconds")
    meters = summary.get("lengthInMeters")
    if seconds is None or meters is None:
        return None, "TomTom gaf geen route."
    return {"meters": meters, "seconds": seconds, "traffic": True}, None


def fmt_distance(meters):
    if meters < 1000:
        return f"{round(meters)} m"
    return f"{meters / 1000:.1f}".replace(".", ",") + " km"


def fmt_duration(seconds):
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} uur" + (f" {rest} min" if rest else "")


def parse_om(value):
    match = re.match(r"^(\d{1,2})[:.](\d{2})$", value.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def explain(settings):
    print("Reistijd is nog niet ingesteld.")
    if not home_of(settings):
        print('Zet eerst je thuisadres: travel huis "<jouw adres>"')
    print("Routes gaan gratis via OSRM, zonder live verkeer.")
    print('Met een TomTom-sleutel komt er file-informatie bij: kluis vraag reistijd --domein api.tomtom.com "TomTom Routing API key"')


def cmd_status(settings):
    home = home_of(settings)
    item = tomtom_item()
    if not home:
        explain(settings)
        return
    print(f"Thuis: {home.get('address') or 'onbekend'} ({home['lat']}, {home['lon']}).")
    if item:
        print("Route: TomTom met live verkeer.")
    else:
        print("Route: OSRM zonder live verkeer.")
    print('Vraag een rit zo: travel naar "<adres>" [--om 14:30]')


def cmd_huis(settings, address):
    address = address.strip()
    if not address:
        print('Gebruik: travel huis "<adres>"')
        return
    place, err = geocode(address)
    if err:
        print(f"Ik kan het adres niet opzoeken: {err}.")
        return
    if not place:
        print(f"Ik vind '{address}' niet. Probeer het met plaatsnaam erbij.")
        return
    settings["home"] = {"address": place["label"] or address, "lat": place["lat"], "lon": place["lon"]}
    save_settings(settings)
    print(f"Thuisadres opgeslagen: {settings['home']['address']}.")


def cmd_naar(settings, address, om):
    home = home_of(settings)
    if not home:
        explain(settings)
        return
    if not address.strip():
        print('Gebruik: travel naar "<adres>" [--om 14:30]')
        return
    place, err = geocode(address)
    if err:
        print(f"Ik kan het adres niet opzoeken: {err}.")
        return
    if not place:
        print(f"Ik vind '{address}' niet. Probeer het met plaatsnaam erbij.")
        return
    departure = None
    arrive_by = None
    if om:
        parsed = parse_om(om)
        if not parsed:
            print("Gebruik voor --om een tijd als 14:30.")
            return
        now = datetime.now()
        arrive_by = now.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0)
        if arrive_by <= now:
            arrive_by += timedelta(days=1)
    item = tomtom_item()
    probe = None
    if item:
        departure_probe = None
        if arrive_by:
            estimate, eerr = route_osrm(home, place)
            if not eerr:
                departure_probe = arrive_by - timedelta(seconds=estimate["seconds"])
        probe, err = route_tomtom(item, home, place, depart_at=departure_probe)
        if err:
            print(f"TomTom lukte niet ({err}); ik probeer OSRM zonder live verkeer.")
            probe = None
    if probe is None:
        probe, err = route_osrm(home, place)
        if err:
            print(f"Ik kan geen route vinden: {err}.")
            return
    line = f"Naar {place['label']}: {fmt_distance(probe['meters'])}, ongeveer {fmt_duration(probe['seconds'])}"
    line += " (met live verkeer)." if probe["traffic"] else " (zonder live verkeer)."
    print(line)
    if arrive_by:
        departure = arrive_by - timedelta(seconds=probe["seconds"])
        if departure.date() != datetime.now().date():
            dagen = ["ma", "di", "wo", "do", "vr", "za", "zo"]
            print(f"Vertrek {dagen[departure.weekday()]} {departure.strftime('%H:%M')} om er om {arrive_by.strftime('%H:%M')} te zijn.")
        else:
            print(f"Vertrek om {departure.strftime('%H:%M')} om er om {arrive_by.strftime('%H:%M')} te zijn.")


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return
    settings = load_settings()
    if not args or args[0] == "status":
        cmd_status(settings)
    elif args[0] == "huis":
        if len(args) < 2:
            print('Gebruik: travel huis "<adres>"')
            return
        cmd_huis(settings, " ".join(args[1:]))
    elif args[0] == "naar":
        rest = args[1:]
        om = None
        if "--om" in rest:
            i = rest.index("--om")
            om = rest[i + 1] if i + 1 < len(rest) else None
            rest = rest[:i] + rest[i + 2:]
        cmd_naar(settings, " ".join(rest), om)
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main()
