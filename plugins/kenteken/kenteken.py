#!/usr/bin/env python3
"""Dutch licence plates, from the RDW's open data: what car it is, and when its APK runs out.

  kenteken <plate>                      make, model, colour, fuel, first registration, APK, insurance, recalls
  kenteken                              the cars you keep, with how long until each APK runs out
  kenteken add <plate> [name]           keep a car (your own, the family's)
  kenteken remove <plate or name>       forget one
  kenteken settings                     the values as JSON
  kenteken settings set cars <list>     replace the whole list, like: 16-RSL-9|Toyota, AB-123-C|Van

The RDW publishes this for every registered vehicle; no key and no account. Owners are never in it.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
VEHICLES = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
FUELS = "https://opendata.rdw.nl/resource/8ys7-d773.json"
DEFAULT = {"cars": ""}
# The RDW writes in Dutch; the command answers in English and Iris says it in the owner's language.
WORDS = {
    "personenauto": "car", "bedrijfsauto": "van", "motorfiets": "motorcycle", "bromfiets": "moped",
    "aanhangwagen": "trailer", "oplegger": "semi-trailer", "bus": "bus", "driewielig motorrijtuig": "three-wheeler",
    "benzine": "petrol", "diesel": "diesel", "elektriciteit": "electric", "lpg": "LPG", "cng": "CNG",
    "waterstof": "hydrogen", "alcohol": "alcohol",
    "zwart": "black", "wit": "white", "grijs": "grey", "blauw": "blue", "rood": "red", "groen": "green",
    "geel": "yellow", "oranje": "orange", "bruin": "brown", "beige": "beige", "paars": "purple", "roze": "pink",
    "creme": "cream", "divers": "multicoloured",
}


def en(value):
    return WORDS.get(value.strip().lower(), value.strip().lower())


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


def plate(text):
    """The plate as the RDW keeps it: letters and digits only, in capitals."""
    p = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if not 4 <= len(p) <= 8:
        sys.exit(f"{text} is not a Dutch licence plate.")
    return p


def pretty(p):
    """16RSL9 as 16-RSL-9: a dash wherever letters and digits meet, and in the middle of four alike."""
    parts = re.findall(r"[A-Z]+|[0-9]+", p)
    out = []
    for part in parts:
        if len(part) == 4:
            out += [part[:2], part[2:]]
        else:
            out.append(part)
    return "-".join(out)


def get(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "Iris-kenteken/1.0", "Accept": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            sys.exit(f"The RDW answered with status {exc.code}. Try again in a minute.")
        except (OSError, ValueError):
            if attempt == 2:
                sys.exit("The RDW did not answer. Try again in a minute.")


def day(value):
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except (TypeError, ValueError, IndexError):
        return None


def apk_text(expires):
    if not expires:
        return "no APK date known"
    days = (expires - date.today()).days
    when = expires.strftime("%d %b %Y")
    if days < 0:
        return f"APK expired on {when}, {-days} days ago"
    if days == 0:
        return f"APK runs out today ({when})"
    if days <= 60:
        return f"APK runs out on {when}, in {days} days: time to book it"
    return f"APK valid until {when}"


def lookup(p):
    rows = get(VEHICLES, {"kenteken": p})
    if not rows:
        return None
    car = rows[0]
    fuels = get(FUELS, {"kenteken": p}) or []
    car["_fuels"] = [f.get("brandstof_omschrijving", "") for f in fuels if f.get("brandstof_omschrijving")]
    return car


# --- commands -------------------------------------------------------------------------------------

def cmd_show(text):
    p = plate(text)
    car = lookup(p)
    if not car:
        print(f"The RDW knows no vehicle with plate {pretty(p)}.")
        return
    name = car.get("handelsbenaming", "")
    make = car.get("merk", "").title()
    model = name.title() if name and not name.upper().startswith(car.get("merk", "").upper()) else name.title()
    kind = en(car.get("voertuigsoort", ""))
    colour = en(car.get("eerste_kleur", ""))
    colour = "" if colour in ("n.v.t.", "niet geregistreerd") else colour
    print(f"{pretty(p)}: {model or make}" + (f", {colour}" if colour else "") + (f" ({kind})" if kind else "") + ".")
    first = day(car.get("datum_eerste_toelating"))
    facts = []
    if first:
        facts.append(f"first on the road {first.strftime('%d %b %Y')}")
    if car["_fuels"]:
        facts.append(" and ".join(en(f) for f in car["_fuels"]))
    if car.get("aantal_zitplaatsen"):
        facts.append(f"{car['aantal_zitplaatsen']} seats")
    if car.get("catalogusprijs"):
        facts.append(f"list price {int(car['catalogusprijs']):,} euro".replace(",", "."))
    if facts:
        line = ", ".join(facts)
        print(line[0].upper() + line[1:] + ".")
    print(apk_text(day(car.get("vervaldatum_apk"))) + ".")
    warnings = []
    if car.get("wam_verzekerd") == "Nee":
        warnings.append("not insured (WAM)")
    if car.get("openstaande_terugroepactie_indicator") == "Ja":
        warnings.append("an open recall: the dealer should fix something")
    if car.get("export_indicator") == "Ja":
        warnings.append("marked for export")
    if car.get("tellerstandoordeel", "").lower().startswith("onlogisch"):
        warnings.append("the odometer reading is marked illogical")
    if warnings:
        print("Note: " + "; ".join(warnings) + ".")


def kept():
    out = []
    for part in values()["cars"].split(","):
        p, _, name = part.strip().partition("|")
        if p.strip():
            out.append((re.sub(r"[^A-Za-z0-9]", "", p).upper(), name.strip()))
    return out


def cmd_list():
    cars = kept()
    if not cars:
        print("No cars kept yet. Keep one with: kenteken add <plate> [name].")
        return
    rows = []
    for p, name in cars:
        car = lookup(p)
        expires = day(car.get("vervaldatum_apk")) if car else None
        rows.append((expires or date.max, p, name, car))
    rows.sort()
    for expires, p, name, car in rows:
        label = name or (car.get("handelsbenaming", "").title() if car else "")
        if not car:
            print(f"{pretty(p)} {label}: unknown at the RDW")
            continue
        print(f"{pretty(p)} ({label}): " + apk_text(None if expires == date.max else expires))


def cmd_add(args):
    if not args:
        sys.exit("kenteken add <plate> [name]")
    p = plate(args[0])
    name = " ".join(args[1:]).strip()
    if "|" in name or "," in name:
        sys.exit("A name cannot hold | or a comma.")
    car = lookup(p)
    if not car:
        sys.exit(f"The RDW knows no vehicle with plate {pretty(p)}.")
    name = name or car.get("handelsbenaming", "").title()
    cars = [c for c in kept() if c[0] != p] + [(p, name)]
    keep("cars", ", ".join(f"{pretty(c)}|{n}" for c, n in cars))
    print(f"Keeping {pretty(p)} ({name}). " + apk_text(day(car.get("vervaldatum_apk"))) + ".")


def cmd_remove(args):
    what = " ".join(args).strip()
    if not what:
        sys.exit("kenteken remove <plate or name>")
    key = re.sub(r"[^A-Za-z0-9]", "", what).upper()
    cars = kept()
    left = [c for c in cars if c[0] != key and c[1].lower() != what.lower()]
    if len(left) == len(cars):
        sys.exit(f"You keep no car called {what}.")
    keep("cars", ", ".join(f"{pretty(c)}|{n}" for c, n in left))
    print(f"Forgot {what}.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] != "cars":
        sys.exit("kenteken settings set cars <plate|name, plate|name>")
    keep("cars", " ".join(args[2:]).strip())
    print(f"{len(kept())} cars kept.")


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
    elif cmd == "settings":
        cmd_settings(rest)
    else:
        cmd_show(" ".join(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
