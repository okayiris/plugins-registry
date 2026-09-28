#!/usr/bin/env python3
"""Your reading list: books you want to read, are reading and have read, found through Open Library.

  books                                 what you are reading now, and how long the to-read list is
  books find <title or author>          look a book up on Open Library
  books want <title or author>          put a book on the to-read list (the best match)
  books start <id or title>             you started reading it
  books done <id or title> [1-5]        you finished it, with stars if you like
  books drop <id or title>              take it off the lists
  books list [want|reading|read]        a list, or all three
  books note <id or title> <text>       keep a thought with a book
  books show <id or title>              one book with its notes
  books year [YYYY]                     what you read in a year

The lists live in data.db next to this file, made from schema.sql the first time. Only the search goes
to Open Library; nothing about your reading leaves the house.
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
SEARCH = "https://openlibrary.org/search.json"
STATES = {"want": "to read", "reading": "reading", "read": "read"}


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    if not con.execute("select 1 from sqlite_master where type='table' and name='books'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def search(query, limit=5):
    params = {"q": query, "limit": limit, "fields": "key,title,author_name,first_publish_year,number_of_pages_median"}
    req = urllib.request.Request(SEARCH + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "Iris-books/1.0 (https://plugins.okayiris.com)"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                docs = json.loads(resp.read().decode()).get("docs") or []
            break
        except (OSError, ValueError, urllib.error.URLError):
            if attempt == 2:
                sys.exit("Open Library did not answer. Try again in a minute.")
    return [{"key": d.get("key", ""), "title": d.get("title", "?"),
             "author": ", ".join((d.get("author_name") or [])[:2]), "year": d.get("first_publish_year"),
             "pages": d.get("number_of_pages_median")} for d in docs]


def label(b):
    by = f" by {b['author']}" if b["author"] else ""
    year = f" ({b['year']})" if b["year"] else ""
    return f"{b['title']}{by}{year}"


def now():
    return datetime.now().isoformat(timespec="seconds")


def pick(con, args, states=None):
    """A book on the lists, by its id or by (a part of) its title."""
    text = " ".join(args).strip()
    if not text:
        sys.exit("Which book? Give its number or its title.")
    if text.lstrip("#").isdigit():
        # "#12" is always the list number; a bare number is a title first (1984), then a list number.
        if not text.startswith("#"):
            titled = con.execute("select * from books where title = ? order by updated desc", (text,)).fetchone()
            if titled:
                return titled
        row = con.execute("select * from books where id = ?", (int(text.lstrip("#")),)).fetchone()
        if row:
            return row
        if text.startswith("#"):
            sys.exit(f"There is no book {text} on your lists.")
        return None
    rows = con.execute("select * from books where lower(title) like ? order by updated desc", (f"%{text.lower()}%",)).fetchall()
    if states:
        rows = [r for r in rows if r["state"] in states] or rows
    if not rows:
        return None
    if len(rows) > 1 and not any(r["title"].lower() == text.lower() for r in rows):
        names = "; ".join(f"#{r['id']} {r['title']}" for r in rows[:5])
        sys.exit(f"Several books fit: {names}. Say the number.")
    return next((r for r in rows if r["title"].lower() == text.lower()), rows[0])


def add_found(con, query, state):
    hits = search(query, 1)
    if not hits:
        sys.exit(f"Open Library has nothing for {query}.")
    b = hits[0]
    existing = con.execute("select * from books where olkey = ? and olkey != ''", (b["key"],)).fetchone()
    if existing:
        return existing, False
    cur = con.execute("insert into books (olkey, title, author, year, pages, state, added, updated) "
                      "values (?, ?, ?, ?, ?, ?, ?, ?)",
                      (b["key"], b["title"], b["author"], b["year"], b["pages"], state, now(), now()))
    return con.execute("select * from books where id = ?", (cur.lastrowid,)).fetchone(), True


def row_line(r):
    stars = f"  {'*' * r['stars']}" if r["stars"] else ""
    return f"#{r['id']}  {label(r)}{stars}"


# --- commands -------------------------------------------------------------------------------------

def cmd_overview():
    with db() as con:
        reading = con.execute("select * from books where state = 'reading' order by updated desc").fetchall()
        want = con.execute("select count(*) from books where state = 'want'").fetchone()[0]
        year = con.execute("select count(*) from books where state = 'read' and finished like ?",
                           (f"{date.today().year}-%",)).fetchone()[0]
    if not reading and not want and not year:
        print("Your lists are empty. Put a book on them with: books want <title>.")
        return
    if reading:
        print("Reading now: " + "; ".join(label(r) for r in reading) + ".")
    else:
        print("Not reading anything right now.")
    print(f"{want} on the to-read list, {year} read this year.")


def cmd_find(args):
    query = " ".join(args).strip()
    if not query:
        sys.exit("books find <title or author>")
    hits = search(query)
    if not hits:
        print(f"Open Library has nothing for {query}.")
        return
    print(f"On Open Library for {query}:")
    for b in hits:
        pages = f", {b['pages']} pages" if b["pages"] else ""
        print(f"  {label(b)}{pages}")


def cmd_want(args):
    query = " ".join(args).strip()
    if not query:
        sys.exit("books want <title or author>")
    with db() as con:
        r, new = add_found(con, query, "want")
    if not new:
        print(f"{label(r)} is already on your {STATES[r['state']]} list, as #{r['id']}.")
        return
    print(f"On the to-read list as #{r['id']}: {label(r)}.")


def cmd_move(args, state, stars=None):
    with db() as con:
        r = pick(con, args, {"want"} if state == "reading" else {"reading", "want"})
        if r is None:
            r, _ = add_found(con, " ".join(args), state)
        fields = {"state": state, "updated": now()}
        if state == "reading" and not r["started"]:
            fields["started"] = date.today().isoformat()
        if state == "read":
            fields["finished"] = date.today().isoformat()
            if stars:
                fields["stars"] = stars
        con.execute("update books set " + ", ".join(f"{k} = ?" for k in fields) + " where id = ?",
                    list(fields.values()) + [r["id"]])
        r = con.execute("select * from books where id = ?", (r["id"],)).fetchone()
        count = con.execute("select count(*) from books where state = 'read' and finished like ?",
                            (f"{date.today().year}-%",)).fetchone()[0]
    if state == "reading":
        print(f"Reading {label(r)}.")
    else:
        took = ""
        if r["started"]:
            days = (date.today() - date.fromisoformat(r["started"])).days
            took = f" in {days} day{'s' if days != 1 else ''}" if days else ", started the same day"
        print(f"Finished {label(r)}{took}. That is {count} this year.")


def cmd_done(args):
    stars = None
    if len(args) > 1 and args[-1].isdigit() and 1 <= int(args[-1]) <= 5:
        stars = int(args[-1])
        args = args[:-1]
    cmd_move(args, "read", stars)


def cmd_drop(args):
    with db() as con:
        r = pick(con, args)
        if r is None:
            sys.exit(f"There is no {' '.join(args)} on your lists.")
        con.execute("delete from notes where book_id = ?", (r["id"],))
        con.execute("delete from books where id = ?", (r["id"],))
    print(f"Dropped {label(r)}.")


def cmd_list(args):
    states = [args[0]] if args and args[0] in STATES else list(STATES)
    with db() as con:
        for s in states:
            order = "finished desc" if s == "read" else "updated desc"
            rows = con.execute(f"select * from books where state = ? order by {order}", (s,)).fetchall()
            if len(states) > 1 and not rows:
                continue
            print(f"{STATES[s].capitalize()} ({len(rows)}):")
            for r in rows[:25]:
                print(f"  {row_line(r)}")
            if not rows:
                print("  nothing")


def cmd_note(args):
    if len(args) < 2:
        sys.exit("books note <id or title> <text>")
    with db() as con:
        if args[0].lstrip("#").isdigit():
            r, text = pick(con, args[:1]), " ".join(args[1:])
        else:
            # The title is as many words as fit a book on the lists.
            r, text = None, ""
            for n in range(len(args) - 1, 0, -1):
                rows = con.execute("select * from books where lower(title) like ?",
                                   (f"%{' '.join(args[:n]).lower()}%",)).fetchall()
                if len(rows) == 1:
                    r, text = rows[0], " ".join(args[n:])
                    break
            if r is None:
                sys.exit("Which book? Give its number first, like: books note 3 <text>.")
        con.execute("insert into notes (book_id, text, created) values (?, ?, ?)", (r["id"], text, now()))
    print(f"Kept with {r['title']}.")


def cmd_show(args):
    with db() as con:
        r = pick(con, args)
        if r is None:
            sys.exit(f"There is no {' '.join(args)} on your lists.")
        notes = con.execute("select * from notes where book_id = ? order by id", (r["id"],)).fetchall()
    print(f"#{r['id']} {label(r)}, {STATES[r['state']]}" + (f", {r['pages']} pages" if r["pages"] else ""))
    if r["started"]:
        print(f"Started {r['started']}" + (f", finished {r['finished']}" if r["finished"] else "") + ".")
    if r["stars"]:
        print(f"{r['stars']} of 5 stars.")
    for n in notes:
        print(f"  {n['created'][:10]}  {n['text']}")
    if r["olkey"]:
        print(f"https://openlibrary.org{r['olkey']}")


def cmd_year(args):
    year = args[0] if args and args[0].isdigit() else str(date.today().year)
    with db() as con:
        rows = con.execute("select * from books where state = 'read' and finished like ? order by finished",
                           (f"{year}-%",)).fetchall()
    if not rows:
        print(f"Nothing finished in {year}.")
        return
    pages = sum(r["pages"] or 0 for r in rows)
    print(f"{len(rows)} book{'s' if len(rows) != 1 else ''} read in {year}" + (f", about {pages:,} pages" if pages else "") + ":")
    for r in rows:
        print(f"  {r['finished'][5:]}  {row_line(r)}")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    commands = {"find": cmd_find, "search": cmd_find, "want": cmd_want, "done": cmd_done, "drop": cmd_drop,
                "list": cmd_list, "note": cmd_note, "show": cmd_show, "year": cmd_year,
                "start": lambda a: cmd_move(a, "reading")}
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd in commands:
        commands[cmd](rest)
    else:
        sys.exit("books want <title>, books start <title>, books done <title>. `books help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
