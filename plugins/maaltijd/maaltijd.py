#!/usr/bin/env python3
"""Meals for the week and the groceries that come with them. Everything stays in the plugin folder.

  maaltijd                              the week overview
  maaltijd plan <dag> "<gerecht>"       put a dish on a day
  maaltijd weg <dag>                    clear a day
  maaltijd recept "<gerecht>" "<ingredienten, gescheiden door komma's>"
  maaltijd recept                       the recipes that are known
  maaltijd recept weg "<gerecht>"       forget a recipe
  maaltijd boodschappen                 all ingredients of the planned dishes, without doubles

Days may be written out (maandag) or short (ma, di), and vandaag, morgen and overmorgen work too.
No keys, no internet: only the little settings.json next to this file.
"""
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
SETTINGS = os.path.join(HERE, "settings.json")

DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


# --- helpers ---------------------------------------------------------------------------------

def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def resolve_day(text):
    t = text.strip().lower()
    today = datetime.now().weekday()
    if t in ("vandaag", "vnd"):
        return DAGEN[today]
    if t == "morgen":
        return DAGEN[(today + 1) % 7]
    if t == "overmorgen":
        return DAGEN[(today + 2) % 7]
    for dag in DAGEN:
        if dag.startswith(t) and len(t) >= 2:
            return dag
    return None


def find_recipe(recepten, dish):
    key = dish.strip().lower()
    for name, ingredients in recepten.items():
        if name.lower() == key:
            return name, ingredients
    return None, None


def ingredients_of(recepten, dish):
    _, ingredients = find_recipe(recepten, dish)
    return ingredients or []


# --- commands --------------------------------------------------------------------------------

def cmd_week():
    data = load_settings()
    week = data.get("week") or {}
    today = DAGEN[datetime.now().weekday()]
    print("Deze week:")
    for dag in DAGEN:
        dish = week.get(dag)
        mark = "  < vandaag" if dag == today else ""
        if dish:
            print(f"  {dag:<10} {dish}{mark}")
        else:
            print(f"  {dag:<10} nog niets{mark}")


def cmd_plan(args):
    rest = args[1:]
    if len(rest) == 1:
        # Only a dish: put it on today.
        dag, dish = DAGEN[datetime.now().weekday()], rest[0]
    elif len(rest) >= 2:
        dag, dish = resolve_day(rest[0]), " ".join(rest[1:])
    else:
        sys.exit('maaltijd plan <dag> "<gerecht>"')
    if not dag:
        sys.exit(f"maaltijd plan: \u201c{rest[0]}\u201d is geen dag. Gebruik maandag tot zondag, of vandaag.")
    data = load_settings()
    week = data.get("week") or {}
    week[dag] = dish
    save_settings(data | {"week": week})
    print(f"{dag} wordt {dish}.")
    if not ingredients_of(data.get("recepten") or {}, dish):
        print(f"Nog geen recept voor {dish}; voeg het toe met `maaltijd recept \"{dish}\" \"...\"`.")


def cmd_weg(args):
    if len(args) < 2:
        sys.exit("maaltijd weg <dag>")
    dag = resolve_day(args[1])
    if not dag:
        sys.exit(f"maaltijd weg: \u201c{args[1]}\u201d is geen dag.")
    data = load_settings()
    week = data.get("week") or {}
    if dag in week:
        del week[dag]
        save_settings(data | {"week": week})
        print(f"{dag} is weer vrij.")
    else:
        print(f"Op {dag} stond niets.")


def cmd_recept(args):
    rest = args[1:]
    recepten = load_settings().get("recepten") or {}
    if not rest:
        if not recepten:
            print("Nog geen recepten. Voeg er een toe met `maaltijd recept \"<gerecht>\" \"<ingredienten>\"`.")
            return
        for name, ingredients in recepten.items():
            print(f"{name}: {', '.join(ingredients)}")
        return
    if rest[0] == "weg":
        if len(rest) < 2:
            sys.exit('maaltijd recept weg "<gerecht>"')
        name, _ = find_recipe(recepten, " ".join(rest[1:]))
        if not name:
            print(f"Geen recept gevonden voor \u201c{' '.join(rest[1:])}\u201d.")
            return
        del recepten[name]
        save_settings(load_settings() | {"recepten": recepten})
        print(f"Recept voor {name} is weg.")
        return
    if len(rest) < 2:
        sys.exit('maaltijd recept "<gerecht>" "<ingredienten, gescheiden door komma\'s>"')
    dish = rest[0]
    ingredients = [x.strip() for x in " ".join(rest[1:]).replace(";", ",").split(",") if x.strip()]
    if not ingredients:
        sys.exit("maaltijd recept: no ingredients given.")
    name, _ = find_recipe(recepten, dish)
    recepten[name or dish] = ingredients
    save_settings(load_settings() | {"recepten": recepten})
    print(f"Recept voor {name or dish} bewaard met {len(ingredients)} ingrediënt(en).")


def cmd_boodschappen():
    data = load_settings()
    week = data.get("week") or {}
    recepten = data.get("recepten") or {}
    seen = {}
    missing = []
    for dag in DAGEN:
        dish = week.get(dag)
        if not dish:
            continue
        ingredients = ingredients_of(recepten, dish)
        if not ingredients:
            missing.append(dish)
            continue
        for item in ingredients:
            key = item.strip().lower()
            if key and key not in seen:
                seen[key] = item.strip()
    if not seen and not missing:
        print("Nog geen maaltijden gepland; de boodschappenlijst is leeg.")
        return
    print("Boodschappen:")
    for item in seen.values():
        print(f"  {item}")
    if missing:
        print("Zonder recept (nog niet meegenomen): " + ", ".join(dict.fromkeys(missing)) + ".")


def main():
    args = sys.argv[1:]
    if not args:
        cmd_week()
    elif args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif args[0] in ("week", "overzicht"):
        cmd_week()
    elif args[0] == "plan":
        cmd_plan(args)
    elif args[0] == "weg":
        cmd_weg(args)
    elif args[0] == "recept":
        cmd_recept(args)
    elif args[0] == "boodschappen":
        cmd_boodschappen()
    else:
        print(f"maaltijd: onbekend commando \u201c{args[0]}\u201d\n")
        print(__doc__.strip())


if __name__ == "__main__":
    main()
