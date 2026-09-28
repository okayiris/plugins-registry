#!/usr/bin/env python3
"""What you spend, said out loud and added up by month and category. Kept in the plugin's own database.

  expenses                              this month: the total, per category, and against your budgets
  expenses add <amount> <category> [note] [yesterday|YYYY-MM-DD]
                                        keep an expense, like: expenses add 12,50 groceries market
  expenses list [YYYY-MM]               every expense of a month, newest first
  expenses month [YYYY-MM]              a month per category, compared with the month before
  expenses remove <id>                  forget an expense
  expenses budget [<category> <amount>] set a monthly budget, or see them (amount 0 removes it)
  expenses categories                   the categories used so far
  expenses settings                     the values as JSON
  expenses settings set currency <code> the currency amounts are shown in

The database is data.db next to this file, made from schema.sql the first time. Amounts are kept in cents.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
DEFAULT = {"currency": "EUR"}


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
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    if not con.execute("select 1 from sqlite_master where type='table' and name='expenses'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def cents(text):
    t = text.strip().lstrip("€$£").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
        return None
    return round(float(t) * 100)


def money(c):
    cur = values()["currency"]
    sign = "-" if c < 0 else ""
    return f"{sign}{abs(c) / 100:,.2f} {cur}"


def month_of(args):
    if args and re.fullmatch(r"\d{4}-\d{2}", args[0]):
        return args[0]
    return date.today().strftime("%Y-%m")


def prev_month(m):
    d = date.fromisoformat(m + "-01") - timedelta(days=1)
    return d.strftime("%Y-%m")


def month_name(m):
    return datetime.strptime(m, "%Y-%m").strftime("%B %Y")


def per_category(con, m):
    rows = con.execute("select category, sum(cents) c, count(*) n from expenses where day like ? "
                       "group by category order by c desc", (m + "-%",)).fetchall()
    return {r["category"]: (r["c"], r["n"]) for r in rows}


def budgets(con):
    return {r["category"]: r["cents"] for r in con.execute("select * from budgets")}


# --- commands -------------------------------------------------------------------------------------

def cmd_overview():
    m = month_of([])
    with db() as con:
        cats = per_category(con, m)
        limits = budgets(con)
    total = sum(c for c, _ in cats.values())
    if not cats:
        print(f"Nothing spent in {month_name(m)} yet. Keep an expense with: expenses add <amount> <category>.")
        return
    print(f"{month_name(m)} so far: {money(total)}.")
    for cat, (c, n) in cats.items():
        line = f"  {cat}: {money(c)}"
        if cat in limits:
            left = limits[cat] - c
            line += f" of {money(limits[cat])}, " + (f"{money(left)} left" if left >= 0 else f"{money(-left)} over")
        print(line)
    for cat in limits:
        if cat not in cats:
            print(f"  {cat}: nothing yet of {money(limits[cat])}")


def cmd_add(args):
    if len(args) < 2:
        sys.exit("expenses add <amount> <category> [note] [yesterday|YYYY-MM-DD]")
    c = cents(args[0])
    if c is None or c <= 0:
        sys.exit(f"{args[0]} is not an amount.")
    rest = list(args[1:])
    day = date.today()
    if rest and rest[-1].lower() in ("today", "yesterday"):
        day = day - timedelta(days=1) if rest.pop().lower() == "yesterday" else day
    elif rest and re.fullmatch(r"\d{4}-\d{2}-\d{2}", rest[-1]):
        try:
            day = date.fromisoformat(rest.pop())
        except ValueError:
            sys.exit("That date does not exist.")
    if not rest:
        sys.exit("Which category? Like: expenses add 12,50 groceries.")
    category, note = rest[0].lower(), " ".join(rest[1:])
    with db() as con:
        cur = con.execute("insert into expenses (day, cents, category, note, created) values (?, ?, ?, ?, ?)",
                          (day.isoformat(), c, category, note, datetime.now().isoformat(timespec="seconds")))
        m = day.strftime("%Y-%m")
        spent = per_category(con, m).get(category, (0, 0))[0]
        limit = budgets(con).get(category)
    when = "" if day == date.today() else f" on {day.strftime('%a %d %b')}"
    period = "this month" if m == date.today().strftime("%Y-%m") else f"in {month_name(m)}"
    line = f"Kept #{cur.lastrowid}: {money(c)} {category}{when}. {category.capitalize()} {period}: {money(spent)}"
    if limit:
        left = limit - spent
        line += f", {money(left)} left of the budget" if left >= 0 else f", {money(-left)} over the budget"
    print(line + ".")


def cmd_list(args):
    m = month_of(args)
    with db() as con:
        rows = con.execute("select * from expenses where day like ? order by day desc, id desc", (m + "-%",)).fetchall()
    if not rows:
        print(f"Nothing in {month_name(m)}.")
        return
    print(f"{month_name(m)}, {len(rows)} expenses, {money(sum(r['cents'] for r in rows))}:")
    for r in rows:
        note = f"  {r['note']}" if r["note"] else ""
        print(f"  #{r['id']}  {date.fromisoformat(r['day']).strftime('%a %d')}  {money(r['cents'])}  {r['category']}{note}")


def cmd_month(args):
    m = month_of(args)
    p = prev_month(m)
    with db() as con:
        now, before = per_category(con, m), per_category(con, p)
    total, total_before = sum(c for c, _ in now.values()), sum(c for c, _ in before.values())
    if not now:
        print(f"Nothing in {month_name(m)}.")
        return
    line = f"{month_name(m)}: {money(total)}"
    if total_before:
        diff = total - total_before
        line += f", {money(abs(diff))} {'more' if diff > 0 else 'less'} than {month_name(p)}"
    print(line + ".")
    for cat in sorted(set(now) | set(before), key=lambda k: -now.get(k, (0, 0))[0]):
        c, b = now.get(cat, (0, 0))[0], before.get(cat, (0, 0))[0]
        share = f" ({c * 100 // total}%)" if total else ""
        was = f", was {money(b)}" if b else ""
        print(f"  {cat}: {money(c)}{share}{was}")


def cmd_remove(args):
    if not args or not args[0].lstrip("#").isdigit():
        sys.exit("expenses remove <id>")
    eid = int(args[0].lstrip("#"))
    with db() as con:
        r = con.execute("select * from expenses where id = ?", (eid,)).fetchone()
        if not r:
            sys.exit(f"There is no expense #{eid}.")
        con.execute("delete from expenses where id = ?", (eid,))
    print(f"Forgot #{eid}: {money(r['cents'])} {r['category']} on {r['day']}.")


def cmd_budget(args):
    with db() as con:
        if not args:
            limits = budgets(con)
            if not limits:
                print("No budgets yet. Set one with: expenses budget <category> <amount>.")
                return
            print("Monthly budgets:")
            for cat, c in sorted(limits.items()):
                print(f"  {cat}: {money(c)}")
            return
        if len(args) < 2:
            sys.exit("expenses budget <category> <amount>")
        category, c = args[0].lower(), cents(args[1])
        if c is None:
            sys.exit(f"{args[1]} is not an amount.")
        if c == 0:
            con.execute("delete from budgets where category = ?", (category,))
            print(f"No budget for {category} any more.")
            return
        con.execute("insert into budgets (category, cents) values (?, ?) "
                    "on conflict (category) do update set cents = excluded.cents", (category, c))
    print(f"The budget for {category} is {money(c)} a month.")


def cmd_categories():
    with db() as con:
        rows = con.execute("select category, count(*) n from expenses group by category order by n desc").fetchall()
    if not rows:
        print("No categories yet.")
        return
    print("Categories: " + ", ".join(f"{r['category']} ({r['n']})" for r in rows) + ".")


def cmd_settings(args):
    if not args:
        print(json.dumps(values()))
        return
    if len(args) < 3 or args[0] != "set" or args[1] != "currency" or not re.fullmatch(r"[A-Za-z]{3}", args[2]):
        sys.exit("expenses settings set currency <three letters, like EUR>")
    keep("currency", args[2].upper())
    print(f"Amounts are shown in {args[2].upper()}.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd == "add":
        cmd_add(rest)
    elif cmd == "list":
        cmd_list(rest)
    elif cmd == "month":
        cmd_month(rest)
    elif cmd in ("remove", "delete"):
        cmd_remove(rest)
    elif cmd == "budget":
        cmd_budget(rest)
    elif cmd == "categories":
        cmd_categories()
    elif cmd == "settings":
        cmd_settings(rest)
    elif cents(cmd) is not None:
        cmd_add(argv)
    else:
        sys.exit("expenses add <amount> <category>. `expenses help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
