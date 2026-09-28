#!/usr/bin/env python3
"""The calendar plugin as a program the house has, for the mailbox scenario.

It is the real plugins/calendar/calendar.py, copied once into $HOME/.sim-calendar with its schema, so its
database lives in the test home and starts empty for every scenario, like a freshly enabled plugin.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
SOURCE = os.path.join(HERE, "..", "..", "plugins", "calendar")
TARGET = os.path.join(os.environ.get("HOME", "."), ".sim-calendar")

if not os.path.exists(os.path.join(TARGET, "calendar.py")):
    os.makedirs(TARGET, exist_ok=True)
    for f in ("calendar.py", "schema.sql"):
        shutil.copy(os.path.join(SOURCE, f), TARGET)
os.execvp(sys.executable, [sys.executable, os.path.join(TARGET, "calendar.py")] + sys.argv[1:])
