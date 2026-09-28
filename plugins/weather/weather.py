#!/usr/bin/env python3
"""The weather where you are, or anywhere else. Free and keyless, through Open-Meteo.

  weather                               now and the next hours at home
  weather <place>                       now and the next hours somewhere else
  weather week [place]                  the next seven days
  weather rain [place]                  will it rain in the next three hours, and when
  weather settings                      the values as JSON
  weather settings set <key> <value>    change one value (place, units)

Home is a place name, looked up once with the Open-Meteo geocoder and kept in values.json next to
this file, together with the coordinates. Nothing else is stored, and no key is needed.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
DEFAULT = {"place": "", "units": "metric"}

# WMO weather interpretation codes, as Open-Meteo returns them.
CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "heavy freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}
AQI = [(20, "good"), (40, "fair"), (60, "moderate"), (80, "poor"), (100, "very poor"), (10**9, "extremely poor")]


# --- values ---------------------------------------------------------------------------------------

def load_values():
    out = dict(DEFAULT)
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            kept = json.load(f)
        if isinstance(kept, dict):
            out.update(kept)
    except (OSError, ValueError):
        pass
    return out


def save_values(data):
    tmp = VALUES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, VALUES_FILE)


# --- the web --------------------------------------------------------------------------------------

def get_json(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "Iris-weather/1.0"})
    # Open-Meteo now and then leaves a connection hanging; the next one is answered at once.
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            sys.exit(f"The weather service answered with status {exc.code}. Try again in a minute.")
        except (OSError, ValueError):
            if attempt == 2:
                sys.exit("The weather service did not answer. Try again in a minute.")


def geocode(name):
    data = get_json(GEOCODE, {"name": name, "count": 1, "format": "json"})
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    parts = []
    for x in (r.get("name"), r.get("admin1"), r.get("country")):
        if x and x not in parts:
            parts.append(x)
    label = ", ".join(parts)
    return {"label": label, "lat": r["latitude"], "lon": r["longitude"], "timezone": r.get("timezone") or "auto"}


def where(args, values):
    """The place asked for, or home."""
    if args:
        place = geocode(" ".join(args))
        if not place:
            sys.exit(f"I could not find a place called {' '.join(args)}.")
        return place
    if values.get("lat") is not None and values.get("lon") is not None:
        return {"label": values.get("label") or values.get("place"), "lat": values["lat"],
                "lon": values["lon"], "timezone": values.get("timezone") or "auto"}
    sys.exit("No home is set yet. Say where you live: weather settings set place <city>.")


def forecast(place, values, **params):
    base = {"latitude": place["lat"], "longitude": place["lon"], "timezone": place["timezone"]}
    if values.get("units") == "imperial":
        base.update({"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"})
    base.update(params)
    return get_json(FORECAST, base)


def units(values):
    if values.get("units") == "imperial":
        return {"t": "°F", "w": "mph", "p": "in"}
    return {"t": "°C", "w": "km/h", "p": "mm"}


def describe(code):
    return CODES.get(code, "unknown weather")


def air_quality(place):
    try:
        req = urllib.request.Request(AIR + "?" + urllib.parse.urlencode(
            {"latitude": place["lat"], "longitude": place["lon"], "current": "european_aqi"}),
            headers={"User-Agent": "Iris-weather/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            value = json.loads(resp.read().decode())["current"]["european_aqi"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if value is None:
        return None
    return next(label for limit, label in AQI if value <= limit)


# --- commands -------------------------------------------------------------------------------------

def cmd_now(args):
    values = load_values()
    place = where(args, values)
    u = units(values)
    data = forecast(place, values,
                    current="temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
                    hourly="temperature_2m,precipitation_probability,weather_code",
                    daily="temperature_2m_max,temperature_2m_min,sunrise,sunset",
                    forecast_days=2)
    cur = data["current"]
    print(f"{place['label']}: {describe(cur['weather_code'])}, {round(cur['temperature_2m'])}{u['t']} "
          f"(feels like {round(cur['apparent_temperature'])}{u['t']}), wind {round(cur['wind_speed_10m'])} {u['w']}.")
    daily = data.get("daily") or {}
    if daily.get("temperature_2m_max"):
        print(f"Today between {round(daily['temperature_2m_min'][0])} and {round(daily['temperature_2m_max'][0])}{u['t']}, "
              f"sun from {daily['sunrise'][0][11:16]} to {daily['sunset'][0][11:16]}.")
    hourly = data.get("hourly") or {}
    now = cur["time"][:13]
    times = hourly.get("time") or []
    start = next((i for i, t in enumerate(times) if t[:13] > now), None)
    if start is not None:
        print("Next hours:")
        for i in range(start, min(start + 6, len(times))):
            chance = hourly["precipitation_probability"][i]
            rain = f", {chance}% rain" if chance else ""
            print(f"  {times[i][11:16]}  {round(hourly['temperature_2m'][i])}{u['t']}  {describe(hourly['weather_code'][i])}{rain}")
    air = air_quality(place)
    if air:
        print(f"Air quality: {air}.")


def cmd_week(args):
    values = load_values()
    place = where(args, values)
    u = units(values)
    data = forecast(place, values,
                    daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                          "precipitation_probability_max,wind_speed_10m_max",
                    forecast_days=7)
    d = data["daily"]
    print(f"{place['label']}, the next seven days:")
    for i, day in enumerate(d["time"]):
        name = "Today" if i == 0 else datetime.fromisoformat(day).strftime("%a %d %b")
        rain = ""
        if d["precipitation_sum"][i]:
            rain = f", {d['precipitation_sum'][i]:g} {u['p']} ({d['precipitation_probability_max'][i]}%)"
        print(f"  {name:<10} {round(d['temperature_2m_min'][i])} to {round(d['temperature_2m_max'][i])}{u['t']}  "
              f"{describe(d['weather_code'][i])}{rain}, wind up to {round(d['wind_speed_10m_max'][i])} {u['w']}")


def cmd_rain(args):
    values = load_values()
    place = where(args, values)
    u = units(values)
    data = forecast(place, values, minutely_15="precipitation", current="precipitation", forecast_hours=3)
    m = data.get("minutely_15") or {}
    times, amounts = m.get("time") or [], m.get("precipitation") or []
    now = (data.get("current") or {}).get("time", "")
    ahead = [(t, a) for t, a in zip(times, amounts) if t >= now[:16]][:12]
    wet = [(t, a) for t, a in ahead if a and a > 0]
    if not wet:
        print(f"{place['label']}: dry for the next three hours.")
        return
    first, last = wet[0][0][11:16], wet[-1][0][11:16]
    total = sum(a for _, a in wet)
    if (data.get("current") or {}).get("precipitation"):
        print(f"{place['label']}: it is raining now, until about {last}; {total:.1f} {u['p']} in total.")
    else:
        print(f"{place['label']}: rain from about {first} until {last}; {total:.1f} {u['p']} in total.")


def cmd_settings(args):
    values = load_values()
    if not args:
        print(json.dumps({"place": values.get("place", ""), "units": values.get("units", "metric")}))
        return
    if len(args) < 3 or args[0] != "set":
        sys.exit("weather settings set <place|units> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "place":
        if not value:
            for k in ("place", "label", "lat", "lon", "timezone"):
                values.pop(k, None)
            values["place"] = ""
            save_values(values)
            print("Home is cleared.")
            return
        place = geocode(value)
        if not place:
            sys.exit(f"I could not find a place called {value}.")
        values.update({"place": value, "label": place["label"], "lat": place["lat"],
                       "lon": place["lon"], "timezone": place["timezone"]})
        save_values(values)
        print(f"Home is {place['label']}.")
    elif key == "units":
        if value not in ("metric", "imperial"):
            sys.exit("Units are metric or imperial.")
        values["units"] = value
        save_values(values)
        print(f"Units are {value}.")
    else:
        sys.exit(f"There is no setting called {key}. Use place or units.")


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return
    if argv and argv[0] == "week":
        cmd_week(argv[1:])
    elif argv and argv[0] == "rain":
        cmd_rain(argv[1:])
    elif argv and argv[0] == "settings":
        cmd_settings(argv[1:])
    else:
        cmd_now(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
