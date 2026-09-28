#!/usr/bin/env python3
"""Recipes to cook tonight, from TheMealDB: search by dish or by what is in the fridge.

  recipes <dish>                        recipes whose name fits, like: recipes lasagna
  recipes with <ingredient>             recipes with that ingredient, like: recipes with chicken
  recipes from <cuisine>                recipes from a kitchen: Italian, Indian, Dutch, Mexican...
  recipes show <number or name>         one recipe: ingredients with amounts, and the steps
  recipes groceries <number or name>    only the ingredients, one line, to put on a shopping list
  recipes random                        a surprise for tonight

No key and no account. Numbers refer to the list printed last.
"""
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
LAST_FILE = os.path.join(HERE, ".last.json")
API = "https://www.themealdb.com/api/json/v1/1/"


def get(path, **params):
    req = urllib.request.Request(API + path + ("?" + urllib.parse.urlencode(params) if params else ""),
                                 headers={"User-Agent": "Iris-recipes/1.0"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode()).get("meals") or []
        except urllib.error.HTTPError as exc:
            sys.exit(f"TheMealDB answered with status {exc.code}. Try again in a minute.")
        except (OSError, ValueError):
            if attempt == 2:
                sys.exit("TheMealDB did not answer. Try again in a minute.")


def remember(meals):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump([{"id": m["idMeal"], "name": m["strMeal"]} for m in meals], f)


def show_list(meals, heading, empty):
    if not meals:
        print(empty)
        return
    meals = meals[:15]
    remember(meals)
    print(heading)
    for n, m in enumerate(meals, 1):
        extra = ", ".join(x for x in (m.get("strArea"), m.get("strCategory")) if x and x != "Unknown")
        print(f"{n:>2}. {m['strMeal']}" + (f" ({extra})" if extra else ""))
    print("Say `recipes show <number>` for the ingredients and the steps.")


def find(ref):
    """A full recipe by its number in the last list, or by its name."""
    text = " ".join(ref).strip()
    if not text:
        sys.exit("Which recipe? Give its number or its name.")
    if text.isdigit():
        try:
            with open(LAST_FILE, encoding="utf-8") as f:
                last = json.load(f)
        except (OSError, ValueError):
            last = []
        n = int(text)
        if not 1 <= n <= len(last):
            sys.exit("That number is not in the last list. Search first.")
        meals = get("lookup.php", i=last[n - 1]["id"])
    else:
        meals = get("search.php", s=text)
        exact = [m for m in meals if m["strMeal"].lower() == text.lower()]
        meals = exact or meals
    if not meals:
        sys.exit(f"TheMealDB has no recipe called {text}.")
    return meals[0]


def ingredients(meal):
    out = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        amount = (meal.get(f"strMeasure{i}") or "").strip()
        if name:
            out.append((name, amount))
    return out


# --- commands -------------------------------------------------------------------------------------

def cmd_search(words):
    text = " ".join(words).strip()
    if not text:
        sys.exit("recipes <dish>, recipes with <ingredient>, recipes from <cuisine>")
    meals = get("search.php", s=text)
    if not meals:
        # Maybe it is an ingredient rather than a dish.
        meals = get("filter.php", i=text.replace(" ", "_"))
    show_list(meals, f"Recipes for {text}:", f"No recipes for {text}. Try an ingredient: recipes with {text}.")


def cmd_with(words):
    text = " ".join(words).strip()
    if not text:
        sys.exit("recipes with <ingredient>")
    show_list(get("filter.php", i=text.replace(" ", "_")), f"Recipes with {text}:", f"No recipes with {text}.")


def cmd_from(words):
    text = " ".join(words).strip()
    if not text:
        sys.exit("recipes from <cuisine>")
    meals = get("filter.php", a=text.title())
    if not meals:
        kitchens = sorted({a["strArea"] for a in get("list.php", a="list")})
        if text.title() in kitchens:
            sys.exit(f"TheMealDB has no {text.title()} recipes yet. Try a dish or an ingredient instead.")
        close = difflib.get_close_matches(text.title(), kitchens, n=4, cutoff=0.6)
        sys.exit(f"TheMealDB knows no {text} kitchen." + (f" Did you mean {', '.join(close)}?" if close else ""))
    show_list(meals, f"From the {text.title()} kitchen:", "")


def cmd_show(ref):
    meal = find(ref)
    extra = ", ".join(x for x in (meal.get("strArea"), meal.get("strCategory")) if x and x != "Unknown")
    print(f"{meal['strMeal']}" + (f" ({extra})" if extra else ""))
    print("Ingredients:")
    for name, amount in ingredients(meal):
        print(f"  {amount + ' ' if amount else ''}{name}")
    print("Steps:")
    steps = [s.strip() for s in re.split(r"\r?\n+", meal.get("strInstructions") or "") if s.strip()]
    steps = [re.sub(r"^(step\s*)?\d+[.)]?\s*", "", s, flags=re.I) for s in steps]
    for n, step in enumerate([s for s in steps if s and not re.fullmatch(r"step\s*\d*", s, re.I)], 1):
        print(f"  {n}. {step}")
    links = [l for l in (meal.get("strSource"), meal.get("strYoutube")) if l]
    if links:
        print(" ".join(links))


def cmd_groceries(ref):
    meal = find(ref)
    print(f"{meal['strMeal']}: " + ", ".join(name.lower() for name, _ in ingredients(meal)))


def cmd_random():
    meal = get("random.php")[0]
    remember([meal])
    extra = ", ".join(x for x in (meal.get("strArea"), meal.get("strCategory")) if x and x != "Unknown")
    print(f"How about {meal['strMeal']}" + (f" ({extra})" if extra else "") + "? Say `recipes show 1` for how to make it.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("", "-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "with":
        cmd_with(rest)
    elif cmd == "from":
        cmd_from(rest)
    elif cmd == "show":
        cmd_show(rest)
    elif cmd == "groceries":
        cmd_groceries(rest)
    elif cmd == "random" and not rest:
        cmd_random()
    else:
        cmd_search(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
