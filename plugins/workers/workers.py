#!/usr/bin/env python3
"""Workers: a short live summary of the workers running for this house.

  workers   one line per running worker, for example "Focus plugin - working 2m 14s"
"""

import json
import shutil
import subprocess
import time

STATUS_WORDS = {
    "werkt": "working",
    "wacht": "waiting",
    "klaar": "done",
    "fout": "stuck",
}
STATUS_ORDER = {"werkt": 0, "wacht": 1, "fout": 2}
DONE = ("klaar", "done")


def status_word(status):
    key = str(status or "").strip().lower()
    if key in STATUS_WORDS:
        return STATUS_WORDS[key]
    return key or "unknown"


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def elapsed(sinds, now):
    total = max(0, int(now - safe_float(sinds)))
    return "{}m {}s".format(total // 60, total % 60)


def load_workers():
    klus = shutil.which("klus")
    if not klus:
        return None
    try:
        result = subprocess.run(
            [klus, "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout or "[]")
    except ValueError:
        return None
    return data if isinstance(data, list) else []


def main():
    workers = load_workers()
    if not workers:
        return
    now = time.time()
    active = [
        item
        for item in workers
        if isinstance(item, dict)
        and str(item.get("status") or "").strip().lower() not in DONE
    ]
    active.sort(
        key=lambda item: (
            STATUS_ORDER.get(str(item.get("status") or "").strip().lower(), 2),
            safe_float(item.get("sinds")),
        )
    )
    for item in active:
        title = str(item.get("titel") or "").strip() or "Untitled"
        print("{} - {} {}".format(title, status_word(item.get("status")), elapsed(item.get("sinds"), now)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
