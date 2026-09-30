#!/usr/bin/env python3
"""A stand-in for the travel plugin, for the planassistant scenario: `travel naar <address> --om HH:MM --json`."""
import json
import sys

args = [a for a in sys.argv[1:] if a != "--json"]
place = args[1] if len(args) > 1 else ""
minutes = {"Jaarbeursplein 6, Utrecht": 17, "Krommerijn 11, Utrecht": 9}.get(place)
if minutes is None:
    print(json.dumps({"error": f"Ik vind '{place}' niet."}))
    sys.exit(0)
print(json.dumps({"from": "Neude 11, Utrecht", "to": place, "meters": minutes * 500, "seconds": minutes * 60,
                  "traffic": False, "leave": None}))
