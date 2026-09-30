#!/usr/bin/env python3
"""A stand-in for the calendars plugin (calendars followed by link), for the planassistant scenario.

Answers `calendars week <n> --json` like calendars 1.1.0 does: a Family calendar and a Work calendar.
"""
import json
import sys
from datetime import date, timedelta

today = date.today()
day = date(2026, 9, 28)   # the scenario's Monday; the appointments stay on it
T, N = day.isoformat(), (day + timedelta(days=1)).isoformat()
events = [
    {"title": "Team call", "start": f"{T}T15:30", "end": f"{T}T16:30", "allday": False, "place": "", "calendar": "Work"},
    {"title": "Swimming", "start": f"{T}T16:00", "end": f"{T}T16:45", "allday": False,
     "place": "Krommerijn 11, Utrecht", "calendar": "Family"},
    {"title": "Parents evening", "start": f"{T}T19:30", "end": f"{T}T20:30", "allday": False, "place": "",
     "calendar": "Family"},
    {"title": "Hockey Sem", "start": f"{N}T18:00", "end": f"{N}T19:15", "allday": False, "place": "",
     "calendar": "Family"},
]
args = [a for a in sys.argv[1:] if a != "--json"]
days = int(args[1]) if len(args) > 1 else 7
last = (today + timedelta(days=days)).isoformat()
print(json.dumps({"from": today.isoformat(), "days": days, "calendars": ["Work", "Family"], "complaints": [],
                  "events": [e for e in events if today.isoformat() <= e["start"][:10] < last]}))
