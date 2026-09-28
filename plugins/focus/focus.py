#!/usr/bin/env python3
"""Focus: a small focus timer with a daily total.

  focus start [minutes]   start a block (25 minutes by default)
  focus pause             pause the running block
  focus resume            resume a paused block
  focus stop              stop and add the minutes to today
  focus or focus status   how much is left, and today's total
  focus today             today's total focused time

State stays in state.json next to this file.
"""

import json
import os
import sys
import time
from datetime import datetime

FOLDER = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(FOLDER, "state.json")
DEFAULT_MINUTES = 25
MAX_MINUTES = 600
USAGE = "Usage: focus start [minutes], focus pause, focus resume, focus stop, focus status, focus today."


def load_state():
    data = {}
    try:
        with open(STATE, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError):
        data = {}
    days = data.get("days")
    if not isinstance(days, dict):
        days = {}
    block = data.get("block")
    if not isinstance(block, dict):
        block = None
    return {"block": block, "days": days}


def save_state(state):
    try:
        with open(STATE, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        pass


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


def day_seconds(state, key):
    try:
        return max(0.0, float(state["days"].get(key, 0)))
    except (TypeError, ValueError):
        return 0.0


def format_span(seconds):
    total = int(round(max(0.0, seconds) / 60.0))
    hours, minutes = divmod(total, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_clock(epoch):
    return datetime.fromtimestamp(epoch).strftime("%H:%M")


def format_count(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def block_total(block):
    try:
        return max(0.0, float(block.get("total", DEFAULT_MINUTES * 60)))
    except (TypeError, ValueError):
        return DEFAULT_MINUTES * 60.0


def block_active(block, now):
    active = 0.0
    try:
        active = float(block.get("active", 0.0))
    except (TypeError, ValueError):
        active = 0.0
    if not block.get("paused"):
        try:
            active += max(0.0, now - float(block.get("last", now)))
        except (TypeError, ValueError):
            pass
    return max(0.0, active)


def cmd_start(args):
    state = load_state()
    if state["block"]:
        print("A focus block is already running.")
        return
    minutes = DEFAULT_MINUTES
    if args:
        try:
            minutes = int(args[0])
        except ValueError:
            print(USAGE)
            return
        if minutes < 1 or minutes > MAX_MINUTES:
            print(USAGE)
            return
    now = time.time()
    state["block"] = {
        "total": minutes * 60.0,
        "active": 0.0,
        "last": now,
        "paused": False,
    }
    save_state(state)
    print(f"Focus block of {format_count(minutes, 'minute')} started. Back at {format_clock(now + minutes * 60)}.")


def cmd_pause(args):
    state = load_state()
    block = state["block"]
    if not block:
        print("No focus block running.")
        return
    if block.get("paused"):
        print("Focus is already paused.")
        return
    now = time.time()
    block["active"] = block_active(block, now)
    block["paused"] = True
    save_state(state)
    print("Focus paused.")


def cmd_resume(args):
    state = load_state()
    block = state["block"]
    if not block:
        print("No focus block running.")
        return
    if not block.get("paused"):
        print("Focus is already running.")
        return
    block["last"] = time.time()
    block["paused"] = False
    save_state(state)
    print("Focus resumed.")


def cmd_stop(args):
    state = load_state()
    block = state["block"]
    if not block:
        print("No focus block running.")
        return
    now = time.time()
    active = min(block_active(block, now), block_total(block))
    key = today_key()
    state["days"][key] = day_seconds(state, key) + active
    state["block"] = None
    save_state(state)
    minutes = int(round(active / 60.0))
    if minutes < 1:
        print(f"Focus stopped. Today: {format_span(day_seconds(state, key))}.")
    else:
        print(f"Focus stopped after {format_count(minutes, 'minute')}. Today: {format_span(day_seconds(state, key))}.")


def cmd_status(args):
    state = load_state()
    block = state["block"]
    if not block:
        print("No focus block running.")
    else:
        now = time.time()
        remaining = max(0.0, block_total(block) - block_active(block, now))
        minutes = int(round(remaining / 60.0))
        if block.get("paused"):
            print(f"Focus paused: {format_count(minutes, 'minute')} left.")
        else:
            print(f"Focus: {format_count(minutes, 'minute')} left, ends at {format_clock(now + remaining)}.")
    print(f"Today: {format_span(day_seconds(state, today_key()))}.")


def cmd_today(args):
    state = load_state()
    print(f"Today: {format_span(day_seconds(state, today_key()))}.")


def main(argv):
    args = argv[1:]
    if not args:
        cmd_status(args)
        return
    action = args[0]
    rest = args[1:]
    if action == "status":
        cmd_status(rest)
    elif action == "start":
        cmd_start(rest)
    elif action == "pause":
        cmd_pause(rest)
    elif action == "resume":
        cmd_resume(rest)
    elif action == "stop":
        cmd_stop(rest)
    elif action == "today":
        cmd_today(rest)
    else:
        print(USAGE)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception:
        print(USAGE)
