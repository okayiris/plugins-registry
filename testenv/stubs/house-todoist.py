#!/usr/bin/env python3
"""A stand-in for the todoist plugin, for the planassistant scenario: `todoist --json`."""
import json

print(json.dumps({"tasks": [{"n": 1, "id": "7", "content": "Call the plumber", "priority": 4, "due": "",
                             "time": "12:00", "when": "today 12:00"}]}))
