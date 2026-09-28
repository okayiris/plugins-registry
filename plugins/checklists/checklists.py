#!/usr/bin/env python3
"""Checklists you use again and again: packing for a trip, the week's chores, what to bring to the pool.

  checklists                            every list, with how far along it is
  checklists new <name> [from <list>]   a new list, empty or a copy of another
  checklists add <list>: <item, item>   put items on a list (a colon after the name, commas between)
  checklists show <list>                one list, what is done and what is still open
  checklists check <list>: <item or n>  tick an item off (by a part of its text, or its number)
  checklists uncheck <list>: <item or n>
  checklists reset <list>               everything open again, to use the list another time
  checklists remove <list>: <item or n> take an item off
  checklists delete <list>              throw a whole list away

Kept in the plugin's own database (data.db, made from schema.sql). Nothing leaves the house.
"""
import os
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    if not con.execute("select 1 from sqlite_master where type='table' and name='lists'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


def split(args):
    """'Packing: towel, sunscreen' as ('Packing', ['towel', 'sunscreen'])."""
    text = " ".join(args).strip()
    if ":" not in text:
        return text, []
    name, _, rest = text.partition(":")
    return name.strip(), [x.strip() for x in rest.split(",") if x.strip()]


def get_list(con, name):
    if not name:
        sys.exit("Which list?")
    rows = con.execute("select * from lists order by name").fetchall()
    exact = [r for r in rows if r["name"].lower() == name.lower()]
    close = exact or [r for r in rows if name.lower() in r["name"].lower()]
    if len(close) == 1:
        return close[0]
    if not rows:
        sys.exit("No lists yet. Start one with: checklists new <name>.")
    if close:
        sys.exit(f"Several lists fit: {', '.join(r['name'] for r in close)}.")
    sys.exit(f"There is no list called {name}. You have: {', '.join(r['name'] for r in rows)}.")


def items(con, lid):
    return con.execute("select * from items where list_id = ? order by position, id", (lid,)).fetchall()


def get_items(con, lst, refs):
    rows = items(con, lst["id"])
    found = []
    for ref in refs:
        if ref.isdigit() and 1 <= int(ref) <= len(rows):
            found.append(rows[int(ref) - 1])
            continue
        exact = [r for r in rows if r["text"].lower() == ref.lower()]
        close = exact or [r for r in rows if ref.lower() in r["text"].lower()]
        if len(close) != 1:
            what = "Several items fit" if close else "No item fits"
            sys.exit(f"{what} {ref!r} on {lst['name']}." + (f" ({', '.join(r['text'] for r in close)})" if close else ""))
        found.append(close[0])
    return found


def progress(con, lid):
    total, done = con.execute("select count(*), coalesce(sum(done), 0) from items where list_id = ?", (lid,)).fetchone()
    return done, total


# --- commands -------------------------------------------------------------------------------------

def cmd_overview():
    with db() as con:
        rows = con.execute("select * from lists order by updated desc").fetchall()
        if not rows:
            print("No lists yet. Start one with: checklists new <name>.")
            return
        print("Your lists:")
        for r in rows:
            done, total = progress(con, r["id"])
            state = "all done" if total and done == total else f"{done} of {total} done"
            print(f"  {r['name']}: {state}")


def cmd_new(args):
    text = " ".join(args).strip()
    source = None
    if " from " in f" {text} ":
        text, _, source = text.partition(" from ")
        text, source = text.strip(), source.strip()
    if not text:
        sys.exit("checklists new <name> [from <list>]")
    if ":" in text:
        sys.exit("A list name cannot hold a colon.")
    with db() as con:
        if con.execute("select 1 from lists where lower(name) = ?", (text.lower(),)).fetchone():
            sys.exit(f"There already is a list called {text}.")
        src = get_list(con, source) if source else None
        cur = con.execute("insert into lists (name, created, updated) values (?, ?, ?)", (text, now(), now()))
        copied = 0
        if src:
            for i, it in enumerate(items(con, src["id"])):
                con.execute("insert into items (list_id, text, done, position) values (?, ?, 0, ?)",
                            (cur.lastrowid, it["text"], i))
                copied += 1
    print(f"New list {text}" + (f", with the {copied} items of {src['name']}." if src else ". Add items with: "
                                 f"checklists add {text}: <item, item>."))


def cmd_add(args):
    name, new = split(args)
    if not new:
        sys.exit("checklists add <list>: <item, item>")
    with db() as con:
        lst = get_list(con, name)
        have = {r["text"].lower() for r in items(con, lst["id"])}
        start = con.execute("select coalesce(max(position), -1) + 1 from items where list_id = ?", (lst["id"],)).fetchone()[0]
        added = [x for x in dict.fromkeys(new) if x.lower() not in have]
        for i, text in enumerate(added):
            con.execute("insert into items (list_id, text, done, position) values (?, ?, 0, ?)", (lst["id"], text, start + i))
        con.execute("update lists set updated = ? where id = ?", (now(), lst["id"]))
        done, total = progress(con, lst["id"])
    skipped = len(new) - len(added)
    print(f"{lst['name']} now has {total} items" + (f" ({skipped} already on it)" if skipped else "") + ".")


def cmd_show(args):
    with db() as con:
        lst = get_list(con, " ".join(args).strip())
        rows = items(con, lst["id"])
        done, total = progress(con, lst["id"])
    if not rows:
        print(f"{lst['name']} is empty.")
        return
    print(f"{lst['name']}, {done} of {total} done:")
    for n, r in enumerate(rows, 1):
        print(f"  {n:>2}. [{'x' if r['done'] else ' '}] {r['text']}")


def cmd_mark(args, done):
    name, refs = split(args)
    if not refs:
        sys.exit(f"checklists {'check' if done else 'uncheck'} <list>: <item or number>")
    with db() as con:
        lst = get_list(con, name)
        hit = get_items(con, lst, refs)
        for r in hit:
            con.execute("update items set done = ? where id = ?", (1 if done else 0, r["id"]))
        con.execute("update lists set updated = ? where id = ?", (now(), lst["id"]))
        d, total = progress(con, lst["id"])
        left = [r["text"] for r in items(con, lst["id"]) if not r["done"]]
    names = ", ".join(r["text"] for r in hit)
    if done and d == total:
        print(f"Ticked off {names}. {lst['name']} is all done.")
    elif done:
        print(f"Ticked off {names}. Still open: {', '.join(left[:8])}" + (" and more." if len(left) > 8 else "."))
    else:
        print(f"{names} open again on {lst['name']}.")


def cmd_reset(args):
    with db() as con:
        lst = get_list(con, " ".join(args).strip())
        con.execute("update items set done = 0 where list_id = ?", (lst["id"],))
        con.execute("update lists set updated = ? where id = ?", (now(), lst["id"]))
        _, total = progress(con, lst["id"])
    print(f"{lst['name']} is open again: {total} items to go.")


def cmd_remove(args):
    name, refs = split(args)
    if not refs:
        sys.exit("checklists remove <list>: <item or number>")
    with db() as con:
        lst = get_list(con, name)
        hit = get_items(con, lst, refs)
        for r in hit:
            con.execute("delete from items where id = ?", (r["id"],))
    print(f"Took {', '.join(r['text'] for r in hit)} off {lst['name']}.")


def cmd_delete(args):
    with db() as con:
        lst = get_list(con, " ".join(args).strip())
        con.execute("delete from items where list_id = ?", (lst["id"],))
        con.execute("delete from lists where id = ?", (lst["id"],))
    print(f"Threw away the list {lst['name']}.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    commands = {"new": cmd_new, "add": cmd_add, "show": cmd_show, "check": lambda a: cmd_mark(a, True),
                "uncheck": lambda a: cmd_mark(a, False), "reset": cmd_reset, "remove": cmd_remove, "delete": cmd_delete}
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd in commands:
        commands[cmd](rest)
    else:
        cmd_show(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
