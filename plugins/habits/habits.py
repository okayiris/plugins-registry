#!/usr/bin/env python3
"""Small daily habits, ticked off by saying so, with streaks. Kept in the plugin's own database.

  habits                                today: what is done and what is still open
  habits add <name>                     start keeping a habit (like walk, read, water)
  habits done <name> [yesterday|date]   tick it off for today, yesterday or a date (YYYY-MM-DD)
  habits undo <name> [yesterday|date]   take a tick back
  habits week                           the last seven days per habit
  habits streaks                        the current and the longest streak per habit
  habits remove <name>                  stop keeping a habit, and forget its ticks

The database is data.db next to this file, made from schema.sql the first time.
"""
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    if not con.execute("select 1 from sqlite_master where type='table' and name='habits'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def habits(con):
    return con.execute("select * from habits order by created, id").fetchall()


def find(con, name):
    name = name.strip().lower()
    rows = habits(con)
    for r in rows:
        if r["name"].lower() == name:
            return r
    close = [r for r in rows if r["name"].lower().startswith(name) or name in r["name"].lower()]
    if len(close) == 1:
        return close[0]
    if not rows:
        sys.exit("No habits yet. Start one with: habits add <name>.")
    sys.exit(f"There is no habit called {name}. You keep: {', '.join(r['name'] for r in rows)}.")


def which_day(words):
    """The day at the end of the words (today, yesterday or YYYY-MM-DD), and the words before it."""
    today = date.today()
    if words and words[-1].lower() in ("today", "yesterday"):
        return (today if words[-1].lower() == "today" else today - timedelta(days=1)), words[:-1]
    if words:
        try:
            d = date.fromisoformat(words[-1])
        except ValueError:
            return today, words
        if d > today:
            sys.exit("That day has not come yet.")
        return d, words[:-1]
    return today, words


def ticks(con, hid):
    return {date.fromisoformat(r[0]) for r in con.execute("select day from checks where habit_id = ?", (hid,))}


def streaks(days):
    """The current streak (counting today if done, else up to yesterday) and the longest one."""
    today = date.today()
    current, d = 0, today if today in days else today - timedelta(days=1)
    while d in days:
        current += 1
        d -= timedelta(days=1)
    longest, run, prev = 0, 0, None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    return current, longest


def day_name(d):
    today = date.today()
    if d == today:
        return "today"
    if d == today - timedelta(days=1):
        return "yesterday"
    return d.strftime("%a %d %b")


# --- commands -------------------------------------------------------------------------------------

def cmd_today():
    today = date.today()
    with db() as con:
        rows = habits(con)
        if not rows:
            print("No habits yet. Start one with: habits add <name>.")
            return
        done, open_ = [], []
        for r in rows:
            days = ticks(con, r["id"])
            current, _ = streaks(days)
            streak = f" ({current} days in a row)" if current > 1 else ""
            (done if today in days else open_).append(r["name"] + streak)
    print(f"Today {len(done)} of {len(rows)} done.")
    if done:
        print("Done: " + ", ".join(done) + ".")
    if open_:
        print("Still open: " + ", ".join(open_) + ".")


def cmd_add(args):
    name = " ".join(args).strip()
    if not name:
        sys.exit("habits add <name>")
    if len(name) > 40:
        sys.exit("Keep the name short, at most 40 letters.")
    with db() as con:
        try:
            con.execute("insert into habits (name, created) values (?, ?)",
                        (name, datetime.now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError:
            sys.exit(f"You already keep {name}.")
    print(f"Keeping {name} from today. Say it when it is done.")


def cmd_done(args, undo=False):
    d, words = which_day(args)
    if not words:
        sys.exit(f"habits {'undo' if undo else 'done'} <name> [yesterday|YYYY-MM-DD]")
    with db() as con:
        r = find(con, " ".join(words))
        if undo:
            gone = con.execute("delete from checks where habit_id = ? and day = ?", (r["id"], d.isoformat())).rowcount
            if not gone:
                print(f"{r['name']} was not ticked off {day_name(d)}.")
                return
            print(f"{r['name']} is open again {day_name(d)}.")
            return
        con.execute("insert or ignore into checks (habit_id, day) values (?, ?)", (r["id"], d.isoformat()))
        current, longest = streaks(ticks(con, r["id"]))
    line = f"{r['name']} done {day_name(d)}."
    if current > 1:
        line += f" {current} days in a row" + (", your longest yet." if current == longest and current > 2 else ".")
    print(line)


def cmd_week():
    today = date.today()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    with db() as con:
        rows = habits(con)
        if not rows:
            print("No habits yet. Start one with: habits add <name>.")
            return
        print("The last seven days (" + " ".join(d.strftime("%a")[:2] for d in days) + "):")
        width = max(len(r["name"]) for r in rows)
        for r in rows:
            got = ticks(con, r["id"])
            marks = " ".join(" x" if d in got else " ." for d in days)
            print(f"  {r['name']:<{width}}  {marks}  {sum(d in got for d in days)} of 7")


def cmd_streaks():
    with db() as con:
        rows = habits(con)
        if not rows:
            print("No habits yet. Start one with: habits add <name>.")
            return
        print("Streaks:")
        for r in rows:
            got = ticks(con, r["id"])
            current, longest = streaks(got)
            print(f"  {r['name']}: now {current} day{'s' if current != 1 else ''}, longest {longest}, "
                  f"{len(got)} in total")


def cmd_remove(args):
    if not args:
        sys.exit("habits remove <name>")
    with db() as con:
        r = find(con, " ".join(args))
        con.execute("delete from checks where habit_id = ?", (r["id"],))
        con.execute("delete from habits where id = ?", (r["id"],))
    print(f"No longer keeping {r['name']}.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd in ("", "today"):
        cmd_today()
    elif cmd == "add":
        cmd_add(rest)
    elif cmd == "done":
        cmd_done(rest)
    elif cmd == "undo":
        cmd_done(rest, undo=True)
    elif cmd == "week":
        cmd_week()
    elif cmd == "streaks":
        cmd_streaks()
    elif cmd in ("remove", "delete"):
        cmd_remove(rest)
    else:
        sys.exit("habits, habits add <name>, habits done <name>. `habits help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
