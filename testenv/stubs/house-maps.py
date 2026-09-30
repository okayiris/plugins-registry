#!/usr/bin/env python3
"""A stand-in for the maps plugin, for the planassistant scenario: `maps route` and `maps find` with --json.

With MAPS_OFF=1 in the environment it answers like maps without a key, so the planner falls back to travel.
"""
import json
import os
import sys

args = [a for a in sys.argv[1:] if a != "--json"]
if os.environ.get("MAPS_OFF"):
    print(json.dumps({"error": "no Google Maps key in the vault yet"}))
    sys.exit(1)
if args[:1] == ["route"]:
    free = [a for a in args[1:] if not a.startswith("--") and a not in ("driving", "walking", "bicycling", "transit")]
    to = free[-1]
    base = {"Jaarbeursplein 6, Utrecht": 14, "Krommerijn 11, Utrecht": 8}.get(to, 20)
    print(json.dumps({"from": free[0] if len(free) > 1 else "Neude 11, Utrecht", "to": to, "mode": "driving",
                      "meters": base * 500, "seconds": base * 60, "traffic_seconds": (base + 6) * 60}))
elif args[:1] == ["find"]:
    kind = args[1]
    places = {
        "parking": [{"name": "Parkeergarage Croeselaan", "address": "Jaarbeursplein 20, Utrecht", "rating": 4.1,
                     "ratings": 900, "open_now": True}],
        "cafe": [{"name": "Miracolo", "address": "Jaarbeursboulevard 256, Utrecht", "rating": 4.4, "ratings": 120,
                  "open_now": True}],
        "restaurant": [{"name": "Pleyn", "address": "Jaarbeursplein 4, Utrecht", "rating": 4.2, "ratings": 300,
                        "open_now": False}],
    }.get(kind, [])
    print(json.dumps({"query": kind, "places": places}))
else:
    print(json.dumps({"error": "maps route or maps find"}))
    sys.exit(1)
