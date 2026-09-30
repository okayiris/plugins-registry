#!/usr/bin/env python3
"""A stand-in for the calendar plugin (this house's own calendar), for the planassistant scenario.

Answers `calendar --json` and `calendar week <n> --json` like calendar 1.0.0 does, with three meetings today.
"""
import json
import sys
from datetime import date, timedelta

today = date.today()
day = date(2026, 9, 28)   # the scenario's Monday; the appointments stay on it
T = day.isoformat()
meetings = [
    {"id": 1, "title": "Client meeting Jansen", "starts": f"{T}T10:00", "ends": f"{T}T11:00",
     "place": "Jaarbeursplein 6, Utrecht", "status": "confirmed"},
    {"id": 2, "title": "Workshop", "starts": f"{T}T12:15", "ends": f"{T}T14:45", "place": "", "status": "confirmed"},
    {"id": 3, "title": "Team call", "starts": f"{T}T15:30", "ends": f"{T}T16:30", "place": "", "status": "confirmed"},
    {"id": 4, "title": "Cancelled lunch", "starts": f"{T}T12:30", "ends": f"{T}T13:30", "place": "",
     "status": "cancelled"},
]
args = [a for a in sys.argv[1:] if a != "--json"]
days = int(args[1]) if args[:1] == ["week"] and len(args) > 1 else 2
last = (today + timedelta(days=days)).isoformat()
print(json.dumps({"today": today.isoformat(), "days": days, "meetings": [m for m in meetings if today.isoformat() <= m["starts"][:10] < last],
                  "invites": []}))
