#!/usr/bin/env python3
"""Quick notes, kept in the plugin's own database. Nothing leaves the house.

  notes                                 the latest notes, pinned ones first
  notes add <text>                      keep a note; words like #work become its tags
  notes find <text>                     notes that hold the text (or a #tag)
  notes show <id>                       one note in full
  notes edit <id> <text>                replace a note's text
  notes append <id> <text>              add a line to a note
  notes pin <id> / notes unpin <id>     keep a note on top, or not
  notes remove <id>                     forget a note
  notes tags                            every tag with how many notes carry it

The database is data.db next to this file, made from schema.sql the first time.
"""
import os
import re
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
TAG = re.compile(r"(?<![\w#])#([\w-]{1,40})", re.UNICODE)


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    if not con.execute("select 1 from sqlite_master where type='table' and name='notes'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


def tags_of(text):
    seen = []
    for t in TAG.findall(text):
        t = t.lower()
        if t not in seen:
            seen.append(t)
    return " ".join(seen)


def one_line(text, width=90):
    line = " ".join(text.split())
    return line if len(line) <= width else line[:width - 3].rsplit(" ", 1)[0] + "..."


def stamp(iso):
    d = datetime.fromisoformat(iso)
    days = (datetime.now().date() - d.date()).days
    if days == 0:
        return d.strftime("today %H:%M")
    if days == 1:
        return d.strftime("yesterday %H:%M")
    if days < 7:
        return d.strftime("%a %H:%M")
    return d.strftime("%d %b %Y")


def note_id(args, usage):
    if not args or not args[0].lstrip("#").isdigit():
        sys.exit(usage)
    return int(args[0].lstrip("#"))


def fetch(con, nid):
    row = con.execute("select * from notes where id = ?", (nid,)).fetchone()
    if not row:
        sys.exit(f"There is no note {nid}.")
    return row


def show_rows(rows, heading, empty):
    if not rows:
        print(empty)
        return
    print(heading)
    for r in rows:
        pin = "* " if r["pinned"] else ""
        print(f"  #{r['id']}  {pin}{one_line(r['text'])}  ({stamp(r['updated'])})")


# --- commands -------------------------------------------------------------------------------------

def cmd_latest():
    with db() as con:
        rows = con.execute("select * from notes order by pinned desc, updated desc limit 15").fetchall()
        total = con.execute("select count(*) from notes").fetchone()[0]
    more = f" (the latest 15 of {total})" if total > 15 else ""
    show_rows(rows, f"Your notes{more}:", "No notes yet. Keep one with: notes add <text>.")


def cmd_add(args):
    text = " ".join(args).strip()
    if not text:
        sys.exit("notes add <text>")
    with db() as con:
        cur = con.execute("insert into notes (text, tags, pinned, created, updated) values (?, ?, 0, ?, ?)",
                          (text, tags_of(text), now(), now()))
    tags = tags_of(text)
    print(f"Kept as note #{cur.lastrowid}" + (f", tagged {tags.replace(' ', ', ')}." if tags else "."))


def cmd_find(args):
    text = " ".join(args).strip()
    if not text:
        sys.exit("notes find <text>")
    with db() as con:
        if text.startswith("#") and " " not in text:
            tag = text[1:].lower()
            rows = con.execute("select * from notes where ' ' || tags || ' ' like ? order by pinned desc, updated desc",
                               (f"% {tag} %",)).fetchall()
        else:
            words = text.lower().split()
            where = " and ".join(["lower(text) like ?"] * len(words))
            rows = con.execute(f"select * from notes where {where} order by pinned desc, updated desc limit 30",
                               [f"%{w}%" for w in words]).fetchall()
    show_rows(rows, f"Notes with {text}:", f"No notes with {text}.")


def cmd_show(args):
    nid = note_id(args, "notes show <id>")
    with db() as con:
        r = fetch(con, nid)
    print(f"Note #{r['id']}, {stamp(r['created'])}" + (f", changed {stamp(r['updated'])}" if r["updated"] != r["created"] else "")
          + (", pinned" if r["pinned"] else ""))
    print(r["text"])


def cmd_edit(args, append=False):
    nid = note_id(args, f"notes {'append' if append else 'edit'} <id> <text>")
    text = " ".join(args[1:]).strip()
    if not text:
        sys.exit(f"notes {'append' if append else 'edit'} <id> <text>")
    with db() as con:
        r = fetch(con, nid)
        new = r["text"] + "\n" + text if append else text
        con.execute("update notes set text = ?, tags = ?, updated = ? where id = ?", (new, tags_of(new), now(), nid))
    print(f"Note #{nid} is changed.")


def cmd_pin(args, on):
    nid = note_id(args, f"notes {'pin' if on else 'unpin'} <id>")
    with db() as con:
        fetch(con, nid)
        con.execute("update notes set pinned = ? where id = ?", (1 if on else 0, nid))
    print(f"Note #{nid} is {'pinned' if on else 'no longer pinned'}.")


def cmd_remove(args):
    nid = note_id(args, "notes remove <id>")
    with db() as con:
        r = fetch(con, nid)
        con.execute("delete from notes where id = ?", (nid,))
    print(f"Forgot note #{nid}: {one_line(r['text'], 60)}")


def cmd_tags():
    counts = {}
    with db() as con:
        for (tags,) in con.execute("select tags from notes where tags != ''"):
            for t in tags.split():
                counts[t] = counts.get(t, 0) + 1
    if not counts:
        print("No tags yet. Put a word like #work in a note to tag it.")
        return
    print("Your tags:")
    for t, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  #{t}  {n} note{'s' if n != 1 else ''}")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_latest()
    elif cmd == "add":
        cmd_add(rest)
    elif cmd in ("find", "search"):
        cmd_find(rest)
    elif cmd == "show":
        cmd_show(rest)
    elif cmd == "edit":
        cmd_edit(rest)
    elif cmd == "append":
        cmd_edit(rest, append=True)
    elif cmd == "pin":
        cmd_pin(rest, True)
    elif cmd == "unpin":
        cmd_pin(rest, False)
    elif cmd in ("remove", "delete"):
        cmd_remove(rest)
    elif cmd == "tags":
        cmd_tags()
    else:
        sys.exit("notes add <text>, notes find <text>, notes show <id>. `notes help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
