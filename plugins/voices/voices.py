#!/usr/bin/env python3
"""Iris' voice: which voices the owner's plan has, and switch. The bridge checks the plan, not this script.

  voices                 the voice you speak with now, and the ones you can choose (also /voices in the chat)
  voices female|male     only women's or men's voices
  voices list [search]   every voice there is, by name, sound or gender (voices list british, voices list deep male),
                         with the plan it is in; the ones outside your plan are marked
  voices try <name> [sentence]   the owner hears that voice on the page, also one of a bigger plan: a demo clip,
                         or your sentence said in it (in their language; it costs a little usage)
  voices use <name>      speak with that voice from your next sentence on: voices use Nora

Iris has 2 voices, Plus 20, Max 200; the free plan speaks with the phone's or browser's own voice, unless it has some.
After switching, say a sentence in the new voice and ask the owner whether they like it. Not sure which one? Let
them hear a few with voices try before switching. Which plan has which voice is decided in the admin panel.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BRIDGE = os.environ.get("IRIS_BRIDGE_URL", "http://host.docker.internal:8790") + "/voices"
MORE = {"free": "Iris (2 voices), Plus (20) or Max (200)", "iris": "Plus (20 voices) or Max (200)", "plus": "Max (200 voices)"}


def call(path="", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BRIDGE + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except ValueError:
            d = {}
        sys.exit(f"voices: {d.get('error') or e.code}")
    except OSError as e:
        sys.exit(f"voices: the connection cannot be reached ({e})")


def show(d, gender=None):
    if not d["voices"]:
        sys.exit(f"The free plan speaks with the phone's or browser's own voice. {MORE['free']} give you voices of your own.")
    now = next((v for v in d["voices"] if v["id"] == d["speaking"]), {"name": d["speaking"] or "the phone's own voice"})
    print(f"Speaking as {now['name']}.")
    if d["chosen"] != d["speaking"]:
        print(f"(Chosen: {d['chosen']}, which this plan no longer has; it comes back with the plan.)")
    shown = [v for v in d["voices"] if not gender or v["gender"] == gender]
    print(f"{len(shown)} voices in this plan:")
    for v in shown:
        print(f"  {v['name']:9} {v['gender']:6} {v['about']}")
    if d["plan"] in MORE:
        print(f"More voices: {MORE[d['plan']]}.")
    print("Switch: voices use <name>")


# Voice tiers keep their old ids (start, pro); the plans are called Iris and Plus.
PLAN = {"free": "Free", "start": "Iris", "pro": "Plus", "max": "Max"}
RANK = {"free": 0, "iris": 1, "start": 1, "plus": 2, "pro": 2, "max": 3}


def search(words):
    d = call("?all=1")
    mine = {v["id"] for v in d["voices"]}
    hits = [v for v in d["catalogue"] if all(w in f"{v['name']} {v['about']} {v['gender']}".lower() for w in words)]
    # male contains "male": a search for women's voices shouldn't also give the men, so gender words match exactly
    if "male" in words or "female" in words:
        g = "female" if "female" in words else "male"
        hits = [v for v in hits if v["gender"] == g]
    if not hits:
        sys.exit(f"voices: no voice matches \"{' '.join(words)}\"")
    hits.sort(key=lambda v: (v["id"] not in mine, RANK.get(v["tier"], 9), v["name"]))
    print(f"{len(hits)} voice(s):")
    for v in hits[:40]:
        where = "" if v["id"] in mine else f"  [{PLAN.get(v['tier'], v['tier'])}]"
        print(f"  {v['name']:9} {v['gender']:6} {v['about']}{where}")
    if len(hits) > 40:
        print(f"  ... and {len(hits) - 40} more; search narrower")
    print("Hear one: voices try <name>. Voices in [brackets] come with that plan.")


def use(name):
    d = call("/choose", {"voice": name})
    print(f"From your next sentence on you speak as {next(v['name'] for v in d['voices'] if v['id'] == d['chosen'])}. "
          "Say something in it and ask the owner whether they like it.")


# Typed in the chat as often as by her, so forgiving: "voices Nora", "voices use Nora", "voices kies nora".
a = sys.argv[1:]
if a and a[0].lower() in ("use", "pick", "choose", "kies", "set"):
    a = ["use", *a[1:]]
if a and a[0].lower() in ("women", "vrouw", "men", "man"):
    a = ["female" if a[0].lower() in ("women", "vrouw") else "male", *a[1:]]
if not a:
    show(call())
elif len(a) == 1 and a[0] in ("female", "male"):
    show(call(), a[0])
elif len(a) == 2 and a[0] == "use":
    use(a[1])
elif len(a) == 1 and a[0] not in ("list", "try"):
    d = call()
    if any(a[0].lower() in (v["id"], v["name"].lower()) for v in d["voices"]):
        use(a[0])
    else:
        show(d)
        print(f'"{a[0]}" is not one of these voices. Find others: voices list {a[0].lower()}')
elif a[0] == "list":
    search([w.lower() for w in a[1:]])
elif a[0] == "try" and len(a) >= 2:
    d = call("/try", {"voice": a[1], "text": " ".join(a[2:])})
    where = "" if d["inPlan"] else f" It comes with {PLAN.get(d['tier'], d['tier'])}, not with the current plan."
    print(f"{d['name']} is playing on the page now ({'a demo clip' if d['demo'] else 'said live'}).{where}")
else:
    show(call())
    print("Switch: voices <name>. Search: voices list <words>. Hear one: voices try <name>.")
