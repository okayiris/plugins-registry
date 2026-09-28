#!/usr/bin/env python3
"""Convert units: length, weight, volume and cooking measures, temperature, speed, area, data, time.

  units <amount> <unit> [to] <unit>     like: units 5 miles km, units 350 F to C, units 2 cups ml
  units <amount> <unit>                 to the usual units on the other side (metric or imperial)
  units list                            every unit that is known, per kind

Offline and exact: no internet, no key. Cups and spoons are US measures.
"""
import re
import sys

# Each unit: (kind, factor to the base unit of that kind). Temperature is handled on its own.
UNITS = {}
PRIMARY = {}


def define(kind, factor, *names):
    for n in names:
        UNITS[n] = (kind, factor)
        PRIMARY[n] = names[0]


# length, base metre
define("length", 1e-3, "mm", "millimeter", "millimeters", "millimetre", "millimetres")
define("length", 1e-2, "cm", "centimeter", "centimeters", "centimetre", "centimetres")
define("length", 1.0, "m", "meter", "meters", "metre", "metres")
define("length", 1e3, "km", "kilometer", "kilometers", "kilometre", "kilometres")
define("length", 0.0254, "in", "inch", "inches", '"')
define("length", 0.3048, "ft", "foot", "feet", "'")
define("length", 0.9144, "yd", "yard", "yards")
define("length", 1609.344, "mi", "mile", "miles")
define("length", 1852.0, "nmi", "nautical mile", "nautical miles")
# mass, base gram
define("mass", 1e-3, "mg", "milligram", "milligrams")
define("mass", 1.0, "g", "gram", "grams")
define("mass", 1e3, "kg", "kilo", "kilos", "kilogram", "kilograms")
define("mass", 1e6, "t", "tonne", "tonnes", "ton")
define("mass", 28.349523125, "oz", "ounce", "ounces")
define("mass", 453.59237, "lb", "lbs", "pound", "pounds")
define("mass", 6350.29318, "st", "stone", "stones")
# volume, base millilitre
define("volume", 1.0, "ml", "milliliter", "milliliters", "millilitre", "millilitres")
define("volume", 10.0, "cl", "centiliter", "centilitre")
define("volume", 100.0, "dl", "deciliter", "decilitre")
define("volume", 1000.0, "l", "liter", "liters", "litre", "litres")
define("volume", 4.92892159375, "tsp", "teaspoon", "teaspoons")
define("volume", 14.78676478125, "tbsp", "tablespoon", "tablespoons")
define("volume", 29.5735295625, "fl oz", "floz", "fluid ounce", "fluid ounces")
define("volume", 236.5882365, "cup", "cups")
define("volume", 473.176473, "pint", "pints", "pt")
define("volume", 3785.411784, "gal", "gallon", "gallons")
define("volume", 568.26125, "uk pint", "imperial pint")
# speed, base metre per second
define("speed", 1.0, "m/s")
define("speed", 1000 / 3600, "km/h", "kmh", "kph")
define("speed", 1609.344 / 3600, "mph")
define("speed", 1852 / 3600, "kn", "knot", "knots")
# area, base square metre
define("area", 1e-4, "cm2", "cm²")
define("area", 1.0, "m2", "m²", "sqm", "square meter", "square meters", "square metre", "square metres")
define("area", 1e4, "ha", "hectare", "hectares")
define("area", 1e6, "km2", "km²")
define("area", 0.09290304, "sqft", "ft2", "ft²", "square foot", "square feet")
define("area", 4046.8564224, "acre", "acres")
define("area", 2589988.110336, "sqmi", "mi2", "square mile", "square miles")
# data, base byte
for i, (short, long_) in enumerate([("b", "byte"), ("kb", "kilobyte"), ("mb", "megabyte"), ("gb", "gigabyte"), ("tb", "terabyte")]):
    define("data", 1000.0 ** i, short, long_, long_ + "s")
for i, short in enumerate(["kib", "mib", "gib", "tib"], 1):
    define("data", 1024.0 ** i, short)
for n, shown in {"b": "B", "kb": "kB", "mb": "MB", "gb": "GB", "tb": "TB", "kib": "KiB", "mib": "MiB", "gib": "GiB", "tib": "TiB"}.items():
    for name, primary in list(PRIMARY.items()):
        if primary == n:
            PRIMARY[name] = shown
# time, base second
define("time", 1.0, "s", "sec", "second", "seconds")
define("time", 60.0, "min", "minute", "minutes")
define("time", 3600.0, "h", "hr", "hour", "hours")
define("time", 86400.0, "d", "day", "days")
define("time", 604800.0, "wk", "week", "weeks")
define("time", 31557600.0, "yr", "year", "years")
# fuel
define("fuel", 1.0, "l/100km")
define("fuel", -1.0, "mpg")

TEMPS = {"c": "°C", "°c": "°C", "celsius": "°C", "f": "°F", "°f": "°F", "fahrenheit": "°F", "k": "K", "kelvin": "K"}
OTHER_SIDE = {"km": "mi", "mi": "km", "m": "ft", "ft": "m", "cm": "in", "in": "cm", "kg": "lb", "lb": "kg",
              "g": "oz", "oz": "g", "l": "gal", "gal": "l", "ml": "fl oz", "fl oz": "ml", "cup": "ml", "tbsp": "ml",
              "tsp": "ml", "km/h": "mph", "mph": "km/h", "m2": "sqft", "sqft": "m2", "ha": "acre", "acre": "ha",
              "st": "kg", "pint": "l", "yd": "m", "l/100km": "mpg", "mpg": "l/100km"}


def canon(unit):
    """The unit as written in UNITS or TEMPS, or None."""
    u = unit.strip().lower().rstrip(".")
    if u in TEMPS:
        return u
    if u in UNITS:
        return u
    if u.endswith("s") and u[:-1] in UNITS:
        return u[:-1]
    return None


def short(unit):
    """The name a unit is printed with: the first one it was defined with."""
    if unit in TEMPS:
        return TEMPS[unit]
    return PRIMARY.get(unit, unit)


def temperature(value, src, dst):
    s, d = TEMPS[src], TEMPS[dst]
    c = value if s == "°C" else (value - 32) * 5 / 9 if s == "°F" else value - 273.15
    return c if d == "°C" else c * 9 / 5 + 32 if d == "°F" else c + 273.15


def fmt(x):
    if x == 0:
        return "0"
    if abs(x) >= 1e6 or abs(x) < 1e-3:
        return f"{x:.4g}"
    if abs(x) >= 100:
        return f"{x:,.1f}".rstrip("0").rstrip(".")
    return f"{x:.3f}".rstrip("0").rstrip(".")


def convert(value, src, dst):
    if src in TEMPS or dst in TEMPS:
        if not (src in TEMPS and dst in TEMPS):
            sys.exit("A temperature only converts to another temperature.")
        return temperature(value, src, dst)
    (k1, f1), (k2, f2) = UNITS[src], UNITS[dst]
    if k1 != k2:
        sys.exit(f"{short(src)} is {k1} and {short(dst)} is {k2}; they do not convert.")
    if k1 == "fuel":
        if f1 == f2:
            return value
        if value == 0:
            sys.exit("Zero does not convert between l/100km and mpg.")
        return 235.214583 / value
    return value * f1 / f2


CONNECTORS = {"to", "in", "into", "naar"}


def number(text):
    """1.5, 1,5 and 1,000 (a comma before exactly three digits groups thousands, as in 1,000 miles)."""
    t = text.replace("_", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif t.count(",") == 1:
        head, _, tail = t.partition(",")
        t = head + tail if len(tail) == 3 else head + "." + tail
    else:
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def parse(args):
    m = re.match(r"^\s*(-?[\d.,_]+)\s*(.*)$", " ".join(args).strip())
    if not m:
        return None
    value = number(m.group(1))
    if value is None:
        return None
    words = m.group(2).split()
    # A connector word only counts between two units: "12 in to cm" and "5 km in miles" both work, and
    # the inch ("in") stays a unit.
    for i, w in enumerate(words):
        if w.lower() in CONNECTORS:
            a, b = " ".join(words[:i]), " ".join(words[i + 1:])
            if canon(a) and canon(b):
                return value, canon(a), canon(b)
    # "5 miles km": two units side by side.
    for i in range(len(words) - 1, 0, -1):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if canon(a) and canon(b):
            return value, canon(a), canon(b)
    left = " ".join(words)
    return (value, canon(left), None) if canon(left) else None


def cmd_list():
    kinds = {}
    for name, (kind, factor) in UNITS.items():
        kinds.setdefault(kind, {}).setdefault(factor, PRIMARY[name])
    kinds["temperature"] = {0: "C", 1: "F", 2: "K"}
    for kind, names in kinds.items():
        print(f"{kind}: {', '.join(names.values())}")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return
    if argv[0] == "list":
        cmd_list()
        return
    parsed = parse(argv)
    if not parsed:
        unknown = [w for w in argv if not re.match(r"^-?[\d.,]+$", w) and not canon(w) and w.lower() not in ("to", "in")]
        sys.exit(f"I do not know the unit {' '.join(unknown) or 'you meant'}. `units list` shows them.")
    value, src, dst = parsed
    if dst is None:
        if src in TEMPS:
            dst = "c" if TEMPS[src] != "°C" else "f"
        else:
            dst = OTHER_SIDE.get(short(src))
            if not dst:
                sys.exit(f"Convert {short(src)} to what? Like: units {fmt(value)} {short(src)} to <unit>.")
    result = convert(value, src, dst)
    print(f"{fmt(value)} {short(src)} = {fmt(result)} {short(dst)}")


if __name__ == "__main__":
    main(sys.argv[1:])
