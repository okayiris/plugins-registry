#!/usr/bin/env python3
"""Keep the hours you work: a timer to start and stop, or hours added afterwards, per project and client,
with an hourly rate. See the day, the week and the month, what is still to invoice, and export a CSV for
your bookkeeping. Kept in the plugin's own database.

  hours                                 the timer, today and this week
  hours start <project> [at 09:15] ["<note>"]   start the timer (stops a running one first)
  hours stop [at 17:30] ["<note>"]      stop the timer
  hours add <2,5|1:30|90m|09:00-12:30> <project> [<day>] ["<note>"]
                                        hours afterwards; a day is today, yesterday, fri or 2026-09-25
  hours edit <id> <hours|project|day|note|billable> <value>
  hours remove <id>
  hours today / hours week [last|-2|2026-W39] / hours month [last|2026-09]
  hours list [today|week|last week|month|last month]   the entries, with their numbers
  hours projects [all]
  hours project add "<name>" [client "<client>"] [rate 85] [nobill]
  hours project edit <project> <name|client|rate|billable> <value>
  hours project archive <project> / restore <project>
  hours invoice <project> [2026-09|all] [done]     what is still to invoice; done marks it invoiced
  hours export [week|last week|month|last month|2026-09|all] [<project>]   a CSV file
  hours settings / hours settings set <key> <value>

A project is its number (#3) or (part of) its name. Adding hours to a name that is not a project yet
makes the project. Times are in the house's own time zone; weeks start on Monday.
"""
import csv
import json
import math
import os
import re
import sqlite3
import sys
from datetime import date, datetime, time, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
EXPORTS = os.path.join(HERE, "exports")
DEFAULT = {"currency": "EUR", "round": "0", "target": "40", "separator": "comma"}
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        "ma": 0, "di": 1, "wo": 2, "do": 3, "vr": 4, "za": 5, "zo": 6,
        "maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3, "vrijdag": 4, "zaterdag": 5, "zondag": 6}
LAST = ("last", "previous", "vorige")


# --- values and database --------------------------------------------------------------------------

def values():
    out = dict(DEFAULT)
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            kept = json.load(f)
        if isinstance(kept, dict):
            out.update({str(k): str(v) for k, v in kept.items()})
    except (OSError, ValueError):
        pass
    return out


def keep(key, value):
    data = {}
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data[key] = value
    with open(VALUES_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def setting(key, low, high):
    try:
        return max(low, min(int(values()[key]), high))
    except ValueError:
        return int(DEFAULT[key])


def db():
    con = sqlite3.connect(DB_FILE, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    if not con.execute("select 1 from sqlite_master where type='table' and name='entries'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def now():
    return datetime.now().astimezone().replace(second=0, microsecond=0)


def iso(dt):
    return dt.isoformat(timespec="minutes")


def parse(value):
    d = datetime.fromisoformat(value)
    return d if d.tzinfo else d.replace(tzinfo=now().tzinfo)


# --- words for time and money ---------------------------------------------------------------------

def hm(minutes):
    return f"{minutes // 60}:{minutes % 60:02d}"


def money(c):
    return f"{c / 100:,.2f} {values()['currency']}"


def cents(text):
    t = text.strip().lstrip("€$£").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
        return None
    return round(float(t) * 100)


def amount(minutes, rate):
    return round(minutes * rate / 60)


def duration(text):
    """Minutes from 2,5 / 2.5 / 1:30 / 90m / 2h / 2u30; None when it is not a length of time."""
    t = text.lower().replace(" ", "")
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if m:
        out = int(m.group(1)) * 60 + int(m.group(2))
    elif re.fullmatch(r"\d+(m|min|mins|minutes?|minuten)", t):
        out = int(re.match(r"\d+", t).group())
    elif re.fullmatch(r"\d{1,2}(h|u)\d{1,2}(m|min)?", t):
        h, rest = re.split(r"[hu]", t, maxsplit=1)
        out = int(h) * 60 + int(re.match(r"\d+", rest).group())
    elif re.fullmatch(r"\d{1,2}([.,]\d+)?(h|u|uur|hours?|hrs?)?", t):
        out = round(float(re.match(r"[\d.,]+", t).group().replace(",", ".")) * 60)
    else:
        return None
    return out if 0 < out <= 24 * 60 else None


def clock(text):
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", text.strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return time(int(m.group(1)), int(m.group(2)))


def span(text):
    """09:00-12:30 as two times, or None."""
    parts = text.replace(" ", "").split("-")
    if len(parts) != 2:
        return None
    a, b = clock(parts[0]), clock(parts[1])
    return (a, b) if a and b and b > a else None


def day_of(text):
    """A day from today, yesterday, fri, 2026-09-25, 25-09 or 25/9. A weekday is the last one that has been."""
    t = text.lower().strip()
    today = now().date()
    if t in ("today", "vandaag"):
        return today
    if t in ("yesterday", "gisteren"):
        return today - timedelta(days=1)
    if t in ("tomorrow", "morgen"):
        return today + timedelta(days=1)
    if t == "eergisteren":
        return today - timedelta(days=2)
    if t in DAYS:
        return today - timedelta(days=(today.weekday() - DAYS[t]) % 7)
    try:
        return date.fromisoformat(t)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})(?:[-/](\d{4}))?", t)
    if m:
        try:
            d = date(int(m.group(3) or today.year), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
        return d.replace(year=d.year - 1) if d > today and not m.group(3) else d
    return None


def day_label(d):
    days = (now().date() - d).days
    return {0: "today", 1: "yesterday"}.get(days) or d.strftime("%a %d %b")


def week_of(args):
    """The Monday of the week meant: this week, last, -2, 2026-W39, or a day in it."""
    monday = now().date() - timedelta(days=now().date().weekday())
    if not args:
        return monday
    t = " ".join(args).lower()
    if t in LAST or t in ("last week", "vorige week"):
        return monday - timedelta(days=7)
    if re.fullmatch(r"-\d{1,2}", t):
        return monday - timedelta(days=7 * int(t[1:]))
    m = re.fullmatch(r"(\d{4})-?w(\d{1,2})", t)
    if m:
        try:
            return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            sys.exit(f"There is no week {t}.")
    d = day_of(t)
    if d:
        return d - timedelta(days=d.weekday())
    sys.exit("hours week [last|-2|2026-W39|<a day>]")


def month_of(args):
    """First and last day of the month meant: this month, last, or 2026-09."""
    today = now().date()
    first = today.replace(day=1)
    t = " ".join(args).lower()
    if t in LAST or t in ("last month", "vorige maand"):
        first = (first - timedelta(days=1)).replace(day=1)
    elif re.fullmatch(r"\d{4}-\d{2}", t):
        try:
            first = date(int(t[:4]), int(t[5:]), 1)
        except ValueError:
            sys.exit(f"There is no month {t}.")
    elif t:
        sys.exit("hours month [last|2026-09]")
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last


# --- projects and entries -------------------------------------------------------------------------

def project(con, ref, make=False):
    ref = str(ref).strip()
    if not ref:
        sys.exit("Which project?")
    if ref.lstrip("#").isdigit():
        p = con.execute("select * from projects where id = ?", (int(ref.lstrip("#")),)).fetchone()
        if not p:
            sys.exit(f"There is no project #{ref.lstrip('#')}.")
        return p
    exact = con.execute("select * from projects where lower(name) = ?", (ref.lower(),)).fetchone()
    if exact:
        return exact
    rows = con.execute("select * from projects where active = 1 and (lower(name) like ? or lower(client) like ?)",
                       (f"%{ref.lower()}%", f"%{ref.lower()}%")).fetchall()
    if len(rows) == 1:
        return rows[0]
    if rows:
        sys.exit(f"Several projects fit {ref}: " + ", ".join(f"#{r['id']} {r['name']}" for r in rows) + ".")
    if not make:
        sys.exit(f"There is no project called {ref}. Make it with: hours project add \"{ref}\".")
    cur = con.execute("insert into projects (name, created) values (?, ?)", (ref[:80], iso(now())))
    print(f"New project #{cur.lastrowid}: {ref[:80]}.")
    return con.execute("select * from projects where id = ?", (cur.lastrowid,)).fetchone()


def minutes_of(e):
    """An entry's minutes; for the running timer, the time so far."""
    if e["running"]:
        return max(int((now() - parse(e["starts"])).total_seconds() // 60), 0)
    return e["minutes"]


def rounded(minutes):
    step = setting("round", 0, 60)
    return math.ceil(minutes / step) * step if step else minutes


def entries(con, first, last, project_id=None):
    sql = ("select e.*, p.name as pname, p.client, coalesce(e.invoiced_rate, p.rate) as rate "
           "from entries e join projects p on p.id = e.project_id "
           "where e.day between ? and ?")
    params = [first.isoformat(), last.isoformat()]
    if project_id:
        sql += " and e.project_id = ?"
        params.append(project_id)
    return con.execute(sql + " order by e.day, coalesce(nullif(e.starts, ''), e.created), e.id", params).fetchall()


def running(con):
    return con.execute("select e.*, p.name as pname from entries e join projects p on p.id = e.project_id "
                       "where e.running = 1 order by e.id desc limit 1").fetchone()


def entry(con, ref):
    if not ref or not ref.lstrip("#").isdigit():
        sys.exit("Which entry? Its number is in hours list.")
    e = con.execute("select e.*, p.name as pname from entries e join projects p on p.id = e.project_id "
                    "where e.id = ?", (int(ref.lstrip("#")),)).fetchone()
    if not e:
        sys.exit(f"There is no entry #{ref.lstrip('#')}.")
    return e


def week_total(con):
    monday = now().date() - timedelta(days=now().date().weekday())
    return sum(minutes_of(e) for e in entries(con, monday, monday + timedelta(days=6)))


def at_time(args):
    """Takes 'at 09:15' out of the words, as a moment today."""
    for i, w in enumerate(args[:-1]):
        if w.lower() in ("at", "om"):
            t = clock(args[i + 1])
            if not t:
                sys.exit(f"{args[i + 1]} is not a time like 09:15.")
            return datetime.combine(now().date(), t).astimezone(), args[:i] + args[i + 2:]
    return None, args


# --- the timer ------------------------------------------------------------------------------------

def stop(con, moment, note=""):
    r = running(con)
    if not r:
        return None
    starts = parse(r["starts"])
    if moment < starts:
        sys.exit(f"The timer started at {starts.strftime('%H:%M')}; it cannot stop before that.")
    minutes = rounded(int((moment - starts).total_seconds() // 60))
    if minutes == 0:
        con.execute("delete from entries where id = ?", (r["id"],))
        print(f"Stopped {r['pname']} after less than a minute; nothing kept.")
        return r
    full = " ".join(x for x in (r["note"], note) if x)
    con.execute("update entries set running = 0, ends = ?, minutes = ?, note = ? where id = ?",
                (iso(moment), minutes, full, r["id"]))
    print(f"Stopped {r['pname']}: {hm(minutes)}, #{r['id']}.")
    return r


def cmd_start(args):
    moment, args = at_time(args)
    moment = moment or now()
    if moment > now():
        sys.exit("A timer can start now or earlier today, not later.")
    with db() as con:
        if args:
            p = project(con, args[0], make=True)
        else:
            last = con.execute("select p.* from entries e join projects p on p.id = e.project_id "
                               "where p.active = 1 order by e.id desc limit 1").fetchone()
            if not last:
                sys.exit("hours start <project>")
            p = last
        stop(con, max(moment, parse(running(con)["starts"])) if running(con) else moment)
        note = " ".join(args[1:]).strip()
        cur = con.execute("insert into entries (project_id, day, starts, running, note, billable, created) "
                          "values (?, ?, ?, 1, ?, ?, ?)",
                          (p["id"], moment.date().isoformat(), iso(moment), note[:300], p["billable"], iso(now())))
        print(f"Timer on {p['name']} since {moment.strftime('%H:%M')} (#{cur.lastrowid}). Stop it with: hours stop.")


def cmd_stop(args):
    moment, args = at_time(args)
    moment = moment or now()
    if moment > now():
        sys.exit("The timer can stop now or earlier, not later.")
    with db() as con:
        if not stop(con, moment, " ".join(args).strip()[:300]):
            sys.exit("No timer is running.")
        print(f"This week: {hm(week_total(con))}.")


# --- adding and changing --------------------------------------------------------------------------

def cmd_add(args):
    if len(args) < 2:
        sys.exit('hours add <2,5|1:30|90m|09:00-12:30> <project> [<day>] ["<note>"]')
    length, times = duration(args[0]), span(args[0])
    if not length and not times:
        sys.exit(f"{args[0]} is not a length of time like 2,5 or 1:30 or 90m, or a span like 09:00-12:30.")
    day, rest = now().date(), args[2:]
    if rest and day_of(rest[0]):
        day, rest = day_of(rest[0]), rest[1:]
    elif rest and re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{1,2}[-/]\d{1,2}([-/]\d{4})?", rest[0]):
        sys.exit(f"{rest[0]} is not a day.")
    if day > now().date():
        sys.exit("Hours are for days that have been; this one is still to come.")
    starts = ends = ""
    if times:
        a, b = (datetime.combine(day, t).astimezone() for t in times)
        if b > now():
            sys.exit(f"{times[1].strftime('%H:%M')} is still to come.")
        starts, ends, length = iso(a), iso(b), int((b - a).total_seconds() // 60)
    note = " ".join(rest).strip()[:300]
    with db() as con:
        p = project(con, args[1], make=True)
        cur = con.execute("insert into entries (project_id, day, starts, ends, minutes, note, billable, created) "
                          "values (?, ?, ?, ?, ?, ?, ?, ?)",
                          (p["id"], day.isoformat(), starts, ends, length, note, p["billable"], iso(now())))
        total = week_total(con)
    print(f"Kept #{cur.lastrowid}: {hm(length)} on {p['name']}, {day_label(day)}"
          + (f", {note}" if note else "") + f". This week: {hm(total)}.")


def cmd_edit(args):
    if len(args) < 3:
        sys.exit("hours edit <id> <hours|project|day|note|billable> <value>")
    field, value = args[1].lower(), " ".join(args[2:]).strip()
    with db() as con:
        e = entry(con, args[0])
        if e["invoiced"] and field != "note":
            sys.exit(f"#{e['id']} is on an invoice since {e['invoiced']}; only its note can change.")
        if field in ("hours", "time", "length", "uren"):
            if e["running"]:
                sys.exit(f"#{e['id']} is the running timer; stop it first.")
            length = duration(value)
            if not length:
                sys.exit(f"{value} is not a length of time like 2,5 or 1:30.")
            con.execute("update entries set minutes = ?, starts = '', ends = '' where id = ?", (length, e["id"]))
            said = hm(length)
        elif field == "project":
            p = project(con, value, make=True)
            con.execute("update entries set project_id = ? where id = ?", (p["id"], e["id"]))
            said = p["name"]
        elif field in ("day", "date", "dag"):
            d = day_of(value)
            if not d or d > now().date():
                sys.exit(f"{value} is not a day that has been.")
            if e["running"]:
                sys.exit(f"#{e['id']} is the running timer; stop it first.")
            con.execute("update entries set day = ?, starts = '', ends = '' where id = ?", (d.isoformat(), e["id"]))
            said = day_label(d)
        elif field == "note":
            con.execute("update entries set note = ? where id = ?", (value[:300], e["id"]))
            said = value or "no note"
        elif field == "billable":
            if value not in ("on", "off", "yes", "no"):
                sys.exit("billable is on or off.")
            con.execute("update entries set billable = ? where id = ?", (int(value in ("on", "yes")), e["id"]))
            said = "billable" if value in ("on", "yes") else "not billable"
        else:
            sys.exit("hours edit <id> <hours|project|day|note|billable> <value>")
    print(f"#{e['id']}: {said}.")


def cmd_remove(args):
    with db() as con:
        e = entry(con, args[0] if args else "")
        if e["invoiced"]:
            sys.exit(f"#{e['id']} is on an invoice since {e['invoiced']}; it stays.")
        con.execute("delete from entries where id = ?", (e["id"],))
    what = "the running timer" if e["running"] else hm(e["minutes"])
    print(f"Removed #{e['id']}: {what} on {e['pname']}, {day_label(date.fromisoformat(e['day']))}.")


# --- seeing ---------------------------------------------------------------------------------------

def per_project(rows):
    out = {}
    for e in rows:
        p = out.setdefault(e["project_id"], {"id": e["project_id"], "name": e["pname"], "client": e["client"],
                                             "minutes": 0, "billable": 0, "amount": 0})
        m = minutes_of(e)
        p["minutes"] += m
        if e["billable"]:
            p["billable"] += m
            p["amount"] += amount(m, e["rate"])
    return sorted(out.values(), key=lambda p: -p["minutes"])


def report(con, first, last, title, by_day):
    rows = entries(con, first, last)
    total = sum(minutes_of(e) for e in rows)
    target = setting("target", 0, 168)
    goal = f" of {target}:00" if target and by_day and (last - first).days == 6 else ""
    print(f"{title}: {hm(total)}{goal}." if rows else f"{title}: no hours yet.")
    if not rows:
        return
    if by_day:
        for i in range((last - first).days + 1):
            d = first + timedelta(days=i)
            todays = [e for e in rows if e["day"] == d.isoformat()]
            if todays:
                split = ", ".join(f"{p['name']} {hm(p['minutes'])}" for p in per_project(todays))
                print(f"  {d.strftime('%a %d %b')}  {hm(sum(minutes_of(e) for e in todays))}  {split}")
        print("Per project:")
    for p in per_project(rows):
        line = f"  {p['name']}" + (f" ({p['client']})" if p["client"] else "") + f"  {hm(p['minutes'])}"
        if p["amount"]:
            line += f"  {money(p['amount'])}"
        print(line)
    billable = sum(minutes_of(e) for e in rows if e["billable"])
    worth = sum(amount(minutes_of(e), e["rate"]) for e in rows if e["billable"])
    if billable != total or worth:
        print(f"Billable: {hm(billable)}" + (f", {money(worth)}" if worth else "")
              + (f". Not billable: {hm(total - billable)}." if total != billable else "."))


def cmd_overview():
    with db() as con:
        r = running(con)
        today = now().date()
        todays = sum(minutes_of(e) for e in entries(con, today, today))
        week = week_total(con)
        monday = today - timedelta(days=today.weekday())
        projects = per_project(entries(con, monday, today))
        known = con.execute("select count(*) from projects where active = 1").fetchone()[0]
    if r:
        so_far = minutes_of(r)
        print(f"Timer: {r['pname']} since {parse(r['starts']).strftime('%H:%M')} ({hm(so_far)})"
              + (f", {r['note']}" if r["note"] else "") + ".")
        if so_far > 10 * 60:
            print("That is a long time: forgot to stop? Say when you stopped with: hours stop at 17:30.")
    else:
        print("No timer running.")
    target = setting("target", 0, 168)
    print(f"Today: {hm(todays)}. This week: {hm(week)}" + (f" of {target}:00." if target else "."))
    for p in projects:
        print(f"  {p['name']}  {hm(p['minutes'])}" + (f"  {money(p['amount'])}" if p["amount"] else ""))
    if not known:
        print('Start with: hours start "<project>", or add hours afterwards with: hours add 2,5 "<project>".')


def cmd_list(args):
    t = " ".join(args).lower()
    today = now().date()
    monday = today - timedelta(days=today.weekday())
    if t in ("today", "vandaag"):
        first, last = today, today
    elif t in ("", "week"):
        first, last = monday, monday + timedelta(days=6)
    elif t in ("last week", "vorige week"):
        first, last = monday - timedelta(days=7), monday - timedelta(days=1)
    elif t.startswith("month") or t.startswith("last month") or re.fullmatch(r"\d{4}-\d{2}", t):
        first, last = month_of([] if t == "month" else ["last"] if t == "last month" else [t])
    else:
        sys.exit("hours list [today|week|last week|month|last month|2026-09]")
    with db() as con:
        rows = entries(con, first, last)
    if not rows:
        print("No hours in that time.")
        return
    for e in rows:
        when = (f"{parse(e['starts']).strftime('%H:%M')}-{parse(e['ends']).strftime('%H:%M')}  "
                if e["starts"] and e["ends"] else "")
        flags = [x for x in ("running" if e["running"] else "", "" if e["billable"] else "not billable",
                             f"invoiced {e['invoiced']}" if e["invoiced"] else "") if x]
        print(f"  #{e['id']}  {date.fromisoformat(e['day']).strftime('%a %d %b')}  {when}{hm(minutes_of(e))}  {e['pname']}"
              + (f", {e['note']}" if e["note"] else "") + (f"  ({', '.join(flags)})" if flags else ""))


def cmd_today(args):
    today = now().date()
    with db() as con:
        report(con, today, today, "Today", False)
    cmd_list(["today"])


def cmd_week(args):
    monday = week_of(args)
    with db() as con:
        report(con, monday, monday + timedelta(days=6),
               f"Week {monday.isocalendar()[1]}, {monday.strftime('%a %d %b')} to "
               f"{(monday + timedelta(days=6)).strftime('%a %d %b')}", True)


def cmd_month(args):
    first, last = month_of(args)
    with db() as con:
        report(con, first, last, first.strftime("%B %Y"), False)


# --- projects -------------------------------------------------------------------------------------

def project_line(con, p):
    first, last = month_of([])
    month = sum(minutes_of(e) for e in entries(con, first, last, p["id"]))
    parts = [p["client"], f"{money(p['rate'])} an hour" if p["rate"] else "",
             "" if p["billable"] else "not billable", "" if p["active"] else "archived",
             f"this month {hm(month)}" if month else ""]
    return f"#{p['id']}  {p['name']}" + "".join(f", {x}" for x in parts if x)


def cmd_projects(args):
    with db() as con:
        rows = con.execute("select * from projects" + ("" if args[:1] == ["all"] else " where active = 1")
                           + " order by active desc, lower(name)").fetchall()
        if not rows:
            print('No projects yet. Add one with: hours project add "Website Bakker" client "Bakker BV" rate 85.')
            return
        for p in rows:
            print("  " + project_line(con, p))


def project_options(rest):
    """client "<c>", rate <amount>, nobill, in any order."""
    out, i = {}, 0
    while i < len(rest):
        w = rest[i].lower()
        if w in ("client", "klant") and i + 1 < len(rest):
            out["client"] = rest[i + 1].strip()[:80]
            i += 2
        elif w in ("rate", "tarief") and i + 1 < len(rest):
            c = cents(rest[i + 1])
            if c is None:
                sys.exit(f"{rest[i + 1]} is not an amount like 85 or 72,50.")
            out["rate"] = c
            i += 2
        elif w in ("nobill", "unbilled", "internal", "intern"):
            out["billable"] = 0
            i += 1
        else:
            sys.exit(f'What is {rest[i]}? hours project add "<name>" [client "<client>"] [rate 85] [nobill]')
    return out


def cmd_project(args):
    if not args:
        return cmd_projects([])
    sub, rest = args[0].lower(), args[1:]
    with db() as con:
        if sub == "add":
            if not rest or not rest[0].strip():
                sys.exit('hours project add "<name>" [client "<client>"] [rate 85] [nobill]')
            name = rest[0].strip()[:80]
            if con.execute("select 1 from projects where lower(name) = ?", (name.lower(),)).fetchone():
                sys.exit(f"There is a project called {name} already.")
            o = project_options(rest[1:])
            cur = con.execute("insert into projects (name, client, rate, billable, created) values (?, ?, ?, ?, ?)",
                              (name, o.get("client", ""), o.get("rate", 0), o.get("billable", 1), iso(now())))
            print("New: " + project_line(con, con.execute("select * from projects where id = ?", (cur.lastrowid,)).fetchone()) + ".")
            return
        if sub in ("archive", "restore"):
            if not rest:
                sys.exit(f"hours project {sub} <project>")
            p = project(con, " ".join(rest))
            con.execute("update projects set active = ? where id = ?", (int(sub == "restore"), p["id"]))
            print(f"{p['name']} is " + ("back among the projects." if sub == "restore" else "archived; its hours stay."))
            return
        if sub == "edit":
            if len(rest) < 3:
                sys.exit("hours project edit <project> <name|client|rate|billable> <value>")
            p = project(con, rest[0])
            field, value = rest[1].lower(), " ".join(rest[2:]).strip()
            if field == "name":
                if not value or con.execute("select 1 from projects where lower(name) = ? and id != ?",
                                            (value.lower(), p["id"])).fetchone():
                    sys.exit(f"There is a project called {value} already." if value else "A project needs a name.")
                con.execute("update projects set name = ? where id = ?", (value[:80], p["id"]))
            elif field in ("client", "klant"):
                con.execute("update projects set client = ? where id = ?", (value[:80], p["id"]))
            elif field in ("rate", "tarief"):
                c = cents(value)
                if c is None:
                    sys.exit(f"{value} is not an amount like 85 or 72,50.")
                con.execute("update projects set rate = ? where id = ?", (c, p["id"]))
            elif field == "billable":
                if value not in ("on", "off"):
                    sys.exit("billable is on or off.")
                con.execute("update projects set billable = ? where id = ?", (int(value == "on"), p["id"]))
            else:
                sys.exit("hours project edit <project> <name|client|rate|billable> <value>")
            print(project_line(con, con.execute("select * from projects where id = ?", (p["id"],)).fetchone()) + ".")
            return
    sys.exit("hours project add|edit|archive|restore ...")


# --- invoicing and export -------------------------------------------------------------------------

def cmd_invoice(args):
    done = bool(args) and args[-1].lower() in ("done", "invoiced", "gefactureerd")
    args = args[:-1] if done else args
    if not args:
        sys.exit("hours invoice <project> [2026-09|last|all] [done]")
    period = "all"
    if len(args) > 1 and (args[-1].lower() in LAST + ("all", "month") or re.fullmatch(r"\d{4}-\d{2}", args[-1])):
        period, args = args[-1].lower(), args[:-1]
    ref = " ".join(args)
    with db() as con:
        p = project(con, ref)
        first, last = (date(2000, 1, 1), now().date()) if period == "all" else month_of([] if period == "month" else [period])
        rows = [e for e in entries(con, first, last, p["id"])
                if e["billable"] and not e["invoiced"] and not e["running"]]
        total = sum(e["minutes"] for e in rows)
        label = "" if period == "all" else f" in {first.strftime('%B %Y')}"
        if not rows:
            print(f"Nothing of {p['name']}{label} is still to invoice.")
            return
        if done:
            con.execute("update entries set invoiced = ?, invoiced_rate = ? where id in (%s)" % ",".join("?" * len(rows)),
                        [now().date().isoformat(), p["rate"]] + [e["id"] for e in rows])
            print(f"Marked {len(rows)} entr{'y' if len(rows) == 1 else 'ies'} of {p['name']} ({hm(total)}) as invoiced.")
            return
    print(f"{p['name']}" + (f" for {p['client']}" if p["client"] else "") + f", still to invoice{label}:")
    for e in rows:
        print(f"  {date.fromisoformat(e['day']).strftime('%a %d %b')}  {hm(e['minutes'])}" + (f"  {e['note']}" if e["note"] else ""))
    line = f"Together {hm(total)} ({total / 60:.2f} hours)"
    if p["rate"]:
        line += f" at {money(p['rate'])} = {money(amount(total, p['rate']))}, before VAT"
    print(line + ".")
    print(f"Once the invoice is out: hours invoice {p['id']}" + ("" if period == "all" else f" {first.strftime('%Y-%m')}") + " done.")


def cmd_export(args):
    t = " ".join(args).lower()
    today = now().date()
    monday = today - timedelta(days=today.weekday())
    ranges = {"week": (monday, monday + timedelta(days=6), f"{monday.isocalendar()[0]}-W{monday.isocalendar()[1]:02d}"),
              "last week": (monday - timedelta(days=7), monday - timedelta(days=1),
                            f"{(monday - timedelta(days=7)).isocalendar()[0]}-W{(monday - timedelta(days=7)).isocalendar()[1]:02d}"),
              "all": (date(2000, 1, 1), today, "all")}
    ref = ""
    for key in ("last week", "last month", "week", "month", "all"):
        if t.startswith(key):
            t, ref = key, " ".join(args)[len(key):].strip()
            break
    else:
        m = re.match(r"(\d{4}-\d{2})\s*(.*)", t)
        if m:
            t, ref = m.group(1), " ".join(args)[len(m.group(1)):].strip()
        else:
            t, ref = "month", " ".join(args).strip()
    if t in ranges:
        first, last, label = ranges[t]
    else:
        first, last = month_of([] if t == "month" else ["last"] if t == "last month" else [t])
        label = first.strftime("%Y-%m")
    semi = values()["separator"] == "semicolon"
    with db() as con:
        p = project(con, ref) if ref else None
        rows = [e for e in entries(con, first, last, p["id"] if p else None) if not e["running"]]
    if not rows:
        print("No hours to export in that time.")
        return
    os.makedirs(EXPORTS, exist_ok=True)
    name = f"hours-{label}" + (f"-{re.sub(r'[^a-z0-9]+', '-', p['name'].lower()).strip('-')}" if p else "") + ".csv"
    path = os.path.join(EXPORTS, name)
    num = (lambda x: f"{x:.2f}".replace(".", ",")) if semi else (lambda x: f"{x:.2f}")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";" if semi else ",")
        w.writerow(["date", "start", "end", "project", "client", "hours", "note", "billable", "rate", "amount", "invoiced"])
        for e in rows:
            worth = amount(e["minutes"], e["rate"]) if e["billable"] else 0
            w.writerow([e["day"], parse(e["starts"]).strftime("%H:%M") if e["starts"] else "",
                        parse(e["ends"]).strftime("%H:%M") if e["ends"] else "", e["pname"], e["client"],
                        num(e["minutes"] / 60), e["note"], "yes" if e["billable"] else "no",
                        num(e["rate"] / 100), num(worth / 100), e["invoiced"]])
    total = sum(e["minutes"] for e in rows)
    home = os.path.expanduser("~")
    shown = "~" + path[len(home):] if home not in ("", "/") and path.startswith(home + os.sep) else path
    print(f"Written {len(rows)} entr{'y' if len(rows) == 1 else 'ies'} ({hm(total)}) to {shown}")


# --- the screen -----------------------------------------------------------------------------------

def cmd_data(args):
    """Everything the screen shows, as JSON: the timer, today, a week (0 this week, -1 the one before)."""
    try:
        offset = max(-520, min(int(args[0]), 0)) if args else 0
    except ValueError:
        offset = 0
    today = now().date()
    monday = today - timedelta(days=today.weekday()) + timedelta(days=7 * offset)
    sunday = monday + timedelta(days=6)
    with db() as con:
        r = running(con)
        rows = entries(con, monday, sunday)
        todays = sum(minutes_of(e) for e in entries(con, today, today))
        projects = con.execute("select p.*, max(e.id) as used from projects p left join entries e on e.project_id = p.id "
                               "where p.active = 1 group by p.id order by used is null, used desc, lower(p.name)").fetchall()
    out = {
        "now": iso(now()), "today": today.isoformat(), "currency": values()["currency"],
        "target": setting("target", 0, 168) * 60, "todayMinutes": todays,
        "running": {"id": r["id"], "project": r["pname"], "projectId": r["project_id"], "starts": r["starts"],
                    "note": r["note"]} if r else None,
        "week": {
            "offset": offset, "start": monday.isoformat(), "end": sunday.isoformat(), "number": monday.isocalendar()[1],
            "days": [{"day": (monday + timedelta(days=i)).isoformat(),
                      "minutes": sum(minutes_of(e) for e in rows if e["day"] == (monday + timedelta(days=i)).isoformat())}
                     for i in range(7)],
            "total": sum(minutes_of(e) for e in rows),
            "billable": sum(minutes_of(e) for e in rows if e["billable"]),
            "amount": sum(amount(minutes_of(e), e["rate"]) for e in rows if e["billable"]),
            "projects": per_project(rows),
        },
        "entries": [{"id": e["id"], "day": e["day"], "project": e["pname"], "projectId": e["project_id"],
                     "minutes": minutes_of(e), "note": e["note"], "billable": bool(e["billable"]),
                     "invoiced": e["invoiced"], "running": bool(e["running"]),
                     "starts": e["starts"], "ends": e["ends"]} for e in reversed(rows)],
        "projects": [{"id": p["id"], "name": p["name"], "client": p["client"], "rate": p["rate"],
                      "billable": bool(p["billable"])} for p in projects],
    }
    print(json.dumps(out, ensure_ascii=False))


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in DEFAULT:
        sys.exit("hours settings set <" + "|".join(DEFAULT) + "> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "currency" and not re.fullmatch(r"[A-Z]{3}", value.upper()):
        sys.exit("A currency is three letters, like EUR.")
    if key in ("round", "target") and not value.isdigit():
        sys.exit(f"{key} is a whole number.")
    if key == "round" and int(value) > 60:
        sys.exit("Round to at most 60 minutes.")
    if key == "target" and int(value) > 168:
        sys.exit("A week has 168 hours.")
    if key == "separator" and value not in ("comma", "semicolon"):
        sys.exit("separator is comma or semicolon.")
    value = value.upper() if key == "currency" else value
    keep(key, value)
    print(f"{key}: {value}.")


def main(argv):
    argv = [a for a in argv if a != "--json"]
    cmd, rest = (argv[0].lower(), argv[1:]) if argv else ("", [])
    commands = {
        "start": cmd_start, "stop": cmd_stop, "add": cmd_add, "edit": cmd_edit, "remove": cmd_remove,
        "delete": cmd_remove, "today": cmd_today, "week": cmd_week, "month": cmd_month, "list": cmd_list,
        "projects": cmd_projects, "project": cmd_project, "invoice": cmd_invoice, "export": cmd_export,
        "data": cmd_data, "settings": cmd_settings,
    }
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd in commands:
        commands[cmd](rest)
    else:
        sys.exit("hours start <project>, hours add 2,5 <project>, hours week. `hours help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
