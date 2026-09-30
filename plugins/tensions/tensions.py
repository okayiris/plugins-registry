#!/usr/bin/env python3
"""Holacracy tensions: the gap you sense, from one of your roles, between how things are and how they could be.

  tensions                                   what is open: per role, the heaviest and the oldest
  tensions add <role>: <text> [options]      note a tension, sensed from that role
      --circle <name>                        the circle it belongs to (else the one in the settings)
      --tactical | --governance              where it goes, when you already know
      --weight 1|2|3                         light, clear (the default) or strong
      --opportunity                          a chance to seize rather than a gap to close
      --since YYYY-MM-DD                     when it was first sensed, when that was before today
  tensions list [--role R] [--circle C] [--tactical|--governance|--untriaged|--opportunities] [--all]
  tensions show <id>
  tensions agenda [tactical|governance] [--circle C]   the agenda for the next meeting, heaviest first
  tensions triage <id> tactical|governance
  tensions weight <id> 1|2|3
  tensions edit <id>: <new text>
  tensions process <id> <outcome>[: <note>]  done; the outcome is one of
      next-action, project, information, help            (tactical)
      role, policy, election                             (governance)
      dropped                                            (it went away by itself)
  tensions reopen <id>
  tensions delete <id>
  tensions roles                             open tensions per role and circle
  tensions --json                            everything the window and the screen draw
  tensions settings [set <key> <value>]      roles, circle, stale_days

Kept in the plugin's own database (data.db, made from schema.sql). Nothing leaves the house.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")

TACTICAL = ("next-action", "project", "information", "help")
GOVERNANCE = ("role", "policy", "election")
OUTCOMES = TACTICAL + GOVERNANCE + ("dropped",)
# What people say for an outcome, to the outcome itself.
OUTCOME_WORDS = {"action": "next-action", "next": "next-action", "nextaction": "next-action", "info": "information",
                 "roles": "role", "accountability": "role", "domain": "role", "policies": "policy",
                 "elect": "election", "drop": "dropped", "gone": "dropped"}
WEIGHTS = {1: "light", 2: "clear", 3: "strong"}
DEFAULTS = {"roles": "", "circle": "", "stale_days": "14"}


# --- settings -------------------------------------------------------------------------------------

def values():
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def keep(key, value):
    v = values()
    v[key] = value
    with open(VALUES_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(v, f, ensure_ascii=False)
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def my_roles():
    return [r.strip() for r in values()["roles"].split(",") if r.strip()]


def stale_days():
    try:
        return max(1, int(float(values()["stale_days"] or 14)))
    except ValueError:
        return 14


# --- the database ---------------------------------------------------------------------------------

def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    if not con.execute("select 1 from sqlite_master where type='table' and name='tensions'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


def age_days(row):
    return max(0, (datetime.now().date() - datetime.fromisoformat(row["sensed"]).date()).days)


def age_text(days):
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days"


def get(con, ref):
    ref = str(ref).lstrip("#")
    if not ref.isdigit():
        sys.exit("Which tension? Give its number, like: tensions show 3.")
    row = con.execute("select * from tensions where id = ?", (int(ref),)).fetchone()
    if not row:
        sys.exit(f"There is no tension {ref}.")
    return row


def order(rows):
    """Heaviest first, then the one waiting longest."""
    return sorted(rows, key=lambda r: (-r["weight"], r["sensed"], r["id"]))


def line(r, stale=None):
    stale = stale_days() if stale is None else stale
    days = age_days(r)
    tags = [r["kind"] or "not triaged", WEIGHTS.get(r["weight"], "clear")]
    if r["opportunity"]:
        tags.append("opportunity")
    if r["status"] == "open" and days > stale:
        tags.append("waiting long")
    where = r["role"] + (f" in {r['circle']}" if r["circle"] else "")
    return f"  {r['id']:>3}. {r['text']} ({where}; {age_text(days)}; {', '.join(tags)})"


# --- options --------------------------------------------------------------------------------------

def options(args, flags=(), valued=()):
    """Split --flags and --key value pairs from the words."""
    words, got = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--") and a[2:] in flags:
            got[a[2:]] = True
        elif a.startswith("--") and a[2:] in valued:
            if i + 1 >= len(args):
                sys.exit(f"{a} needs a value.")
            got[a[2:]] = args[i + 1]
            i += 1
        elif a.startswith("--"):
            sys.exit(f"Unknown option {a}. See: tensions --help.")
        else:
            words.append(a)
        i += 1
    return words, got


def pick_role(given):
    """The role as it is written in the settings, when it is one of the owner's."""
    roles = my_roles()
    if not given:
        if len(roles) == 1:
            return roles[0]
        hint = f" Your roles: {', '.join(roles)}." if roles else ""
        sys.exit("From which role do you sense this? tensions add <role>: <text>." + hint)
    exact = [r for r in roles if r.lower() == given.lower()]
    close = exact or [r for r in roles if given.lower() in r.lower()]
    return close[0] if len(close) == 1 else given


def weight(value):
    if str(value) not in ("1", "2", "3"):
        sys.exit("The weight is 1 (light), 2 (clear) or 3 (strong).")
    return int(value)


def outcome(word):
    w = word.lower().strip().rstrip(":")
    w = OUTCOME_WORDS.get(w.replace("-", "").replace(" ", ""), w)
    if w not in OUTCOMES:
        sys.exit(f"The outcome is one of: {', '.join(OUTCOMES)}.")
    return w


# --- commands -------------------------------------------------------------------------------------

def cmd_overview():
    with db() as con:
        rows = order(con.execute("select * from tensions where status = 'open'").fetchall())
    if not rows:
        print("No open tensions. When something could be better, say so: tensions add <role>: <text>.")
        return
    stale = stale_days()
    tactical = sum(r["kind"] == "tactical" for r in rows)
    governance = sum(r["kind"] == "governance" for r in rows)
    loose = len(rows) - tactical - governance
    waiting = [r for r in rows if age_days(r) > stale]
    print(f"{len(rows)} open tension{'s' if len(rows) != 1 else ''}: {tactical} tactical, {governance} governance"
          + (f", {loose} not triaged yet" if loose else "") + ".")
    per_role = {}
    for r in rows:
        per_role.setdefault(r["role"], []).append(r)
    for role, own in sorted(per_role.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        print(f"{role or 'No role'} ({len(own)}):")
        for r in own[:5]:
            print(line(r, stale))
        if len(own) > 5:
            print(f"  and {len(own) - 5} more: tensions list --role \"{role}\"")
    if waiting:
        print(f"Waiting longer than {stale} days: {', '.join(str(r['id']) for r in waiting)}.")


def cmd_add(args):
    words, opt = options(args, flags=("tactical", "governance", "opportunity"), valued=("circle", "weight", "role", "since"))
    text = " ".join(words).strip()
    role = opt.get("role", "")
    if ":" in text and not role:
        role, _, text = text.partition(":")
    role, text = role.strip(), text.strip()
    if not text:
        sys.exit("tensions add <role>: <what could be better>")
    if opt.get("tactical") and opt.get("governance"):
        sys.exit("Tactical or governance, not both.")
    role = pick_role(role)
    kind = "tactical" if opt.get("tactical") else "governance" if opt.get("governance") else ""
    w = weight(opt["weight"]) if "weight" in opt else 2
    circle = (opt.get("circle") or values()["circle"] or "").strip()
    sensed = now()
    if opt.get("since"):
        try:
            day = datetime.fromisoformat(opt["since"]).date()
        except ValueError:
            sys.exit("--since takes a date like 2026-09-21.")
        if day > datetime.now().date():
            sys.exit("--since cannot be in the future.")
        sensed = f"{day.isoformat()}T{sensed[11:]}" if day != datetime.now().date() else sensed
    with db() as con:
        cur = con.execute("insert into tensions (text, role, circle, kind, weight, opportunity, sensed) "
                          "values (?, ?, ?, ?, ?, ?, ?)",
                          (text, role, circle, kind, w, 1 if opt.get("opportunity") else 0, sensed))
        n = con.execute("select count(*) from tensions where status = 'open'").fetchone()[0]
    where = f"{role}" + (f" in {circle}" if circle else "")
    print(f"Tension {cur.lastrowid} noted, from {where}" + (f", for {kind}" if kind else ", not triaged yet")
          + f". {n} open now.")


def cmd_list(args):
    words, opt = options(args, flags=("tactical", "governance", "untriaged", "opportunities", "all"),
                         valued=("role", "circle"))
    if words and "role" not in opt:
        opt["role"] = " ".join(words)
    with db() as con:
        rows = con.execute("select * from tensions" + ("" if opt.get("all") else " where status = 'open'")).fetchall()
    what = []
    if opt.get("role"):
        rows = [r for r in rows if opt["role"].lower() in r["role"].lower()]
        what.append(f"from {opt['role']}")
    if opt.get("circle"):
        rows = [r for r in rows if opt["circle"].lower() in r["circle"].lower()]
        what.append(f"in {opt['circle']}")
    for k in ("tactical", "governance"):
        if opt.get(k):
            rows = [r for r in rows if r["kind"] == k]
            what.insert(0, k)
    if opt.get("untriaged"):
        rows = [r for r in rows if not r["kind"]]
        what.insert(0, "not triaged")
    if opt.get("opportunities"):
        rows = [r for r in rows if r["opportunity"]]
        what.insert(0, "opportunities")
    label = " ".join(what)
    if not rows:
        print(f"No {'' if opt.get('all') else 'open '}tensions{' ' + label if label else ''}.")
        return
    open_rows = order([r for r in rows if r["status"] == "open"])
    done = sorted([r for r in rows if r["status"] != "open"], key=lambda r: r["processed"], reverse=True)
    print(f"{len(open_rows)} open{' ' + label if label else ''}:" if open_rows else f"None open{' ' + label if label else ''}.")
    for r in open_rows:
        print(line(r))
    if done:
        print(f"{len(done)} processed:")
        for r in done[:20]:
            print(f"  {r['id']:>3}. {r['text']} ({r['role']}; {r['outcome']}"
                  + (f": {r['note']}" if r["note"] else "") + ")")


def cmd_show(args):
    with db() as con:
        r = get(con, (args or [""])[0])
    print(f"Tension {r['id']}: {r['text']}")
    print(f"  From the role {r['role'] or 'unknown'}" + (f" in {r['circle']}" if r["circle"] else "") + ".")
    print(f"  {'An opportunity' if r['opportunity'] else 'A gap'}, {WEIGHTS.get(r['weight'], 'clear')}, "
          f"{r['kind'] or 'not triaged yet'}; sensed {r['sensed'][:10]} ({age_text(age_days(r))} ago).".replace("(today ago)", "(today)"))
    if r["status"] == "open":
        print("  Still open.")
    else:
        print(f"  Processed {r['processed'][:10]} as {r['outcome']}" + (f": {r['note']}" if r["note"] else "") + ".")


def cmd_agenda(args):
    words, opt = options(args, valued=("circle",))
    kind = (words[0].lower() if words else "")
    if kind not in ("", "tactical", "governance"):
        sys.exit("tensions agenda [tactical|governance] [--circle C]")
    with db() as con:
        rows = con.execute("select * from tensions where status = 'open'").fetchall()
    if opt.get("circle"):
        rows = [r for r in rows if opt["circle"].lower() in r["circle"].lower()]
    loose = [r for r in rows if not r["kind"]]
    kinds = [kind] if kind else ["tactical", "governance"]
    said = False
    for k in kinds:
        items = order([r for r in rows if r["kind"] == k])
        meeting = "Tactical meeting" if k == "tactical" else "Governance meeting"
        if not items:
            print(f"{meeting}: nothing on the agenda.")
            continue
        said = True
        print(f"{meeting}, {len(items)} item{'s' if len(items) != 1 else ''}:")
        for n, r in enumerate(items, 1):
            print(f"  {n}. {short(r['text'])} [{r['id']}] ({r['role']}, {WEIGHTS.get(r['weight'], 'clear')})")
    if loose:
        print(f"Not triaged yet, so on no agenda: {', '.join(str(r['id']) for r in order(loose))}. "
              "Say for each whether it is tactical or governance.")
    elif not said:
        print("Nothing to bring in yet.")


def short(text, words=8):
    parts = text.split()
    return " ".join(parts[:words]) + ("..." if len(parts) > words else "")


def cmd_triage(args):
    if len(args) < 2 or args[1].lower() not in ("tactical", "governance"):
        sys.exit("tensions triage <id> tactical|governance")
    kind = args[1].lower()
    with db() as con:
        r = get(con, args[0])
        con.execute("update tensions set kind = ? where id = ?", (kind, r["id"]))
    print(f"Tension {r['id']} goes to the {kind} meeting.")


def cmd_weight(args):
    if len(args) < 2:
        sys.exit("tensions weight <id> 1|2|3")
    w = weight(args[1])
    with db() as con:
        r = get(con, args[0])
        con.execute("update tensions set weight = ? where id = ?", (w, r["id"]))
    print(f"Tension {r['id']} is {WEIGHTS[w]} now.")


def cmd_edit(args):
    text = " ".join(args)
    ref, _, new = text.partition(":")
    if not new.strip():
        sys.exit("tensions edit <id>: <new text>")
    with db() as con:
        r = get(con, ref.strip())
        con.execute("update tensions set text = ? where id = ?", (new.strip(), r["id"]))
    print(f"Tension {r['id']} now reads: {new.strip()}")


def cmd_process(args):
    text = " ".join(args)
    head, _, note = text.partition(":")
    words = head.split()
    if len(words) < 2:
        sys.exit("tensions process <id> <outcome>[: <note>], the outcome one of: " + ", ".join(OUTCOMES) + ".")
    ref, out = words[0], outcome(" ".join(words[1:]))
    with db() as con:
        r = get(con, ref)
        if r["status"] != "open":
            sys.exit(f"Tension {r['id']} was already processed as {r['outcome']}. Reopen it first: tensions reopen {r['id']}.")
        kind = "tactical" if out in TACTICAL else "governance" if out in GOVERNANCE else r["kind"]
        con.execute("update tensions set status = 'processed', outcome = ?, note = ?, kind = ?, processed = ? where id = ?",
                    (out, note.strip(), kind, now(), r["id"]))
        left = con.execute("select count(*) from tensions where status = 'open'").fetchone()[0]
    print(f"Tension {r['id']} processed: {out}" + (f", {note.strip()}" if note.strip() else "")
          + f". {left} still open.")


def cmd_reopen(args):
    with db() as con:
        r = get(con, (args or [""])[0])
        con.execute("update tensions set status = 'open', outcome = '', note = '', processed = '' where id = ?", (r["id"],))
    print(f"Tension {r['id']} is open again.")


def cmd_delete(args):
    with db() as con:
        r = get(con, (args or [""])[0])
        con.execute("delete from tensions where id = ?", (r["id"],))
    print(f"Threw away tension {r['id']}: {r['text']}")


def cmd_roles():
    with db() as con:
        rows = con.execute("select * from tensions where status = 'open'").fetchall()
    roles = {r: [] for r in my_roles()}
    for r in rows:
        roles.setdefault(r["role"], []).append(r)
    if not roles:
        print("No roles and no open tensions yet. Set your roles: tensions settings set roles <role, role>.")
        return
    print("Open tensions per role:")
    for role, own in sorted(roles.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        circles = sorted({r["circle"] for r in own if r["circle"]})
        print(f"  {role or 'No role'}: {len(own) or 'none'}" + (f" (in {', '.join(circles)})" if circles else ""))


def cmd_json():
    stale = stale_days()
    with db() as con:
        rows = con.execute("select * from tensions").fetchall()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")

    def item(r):
        return {"id": r["id"], "text": r["text"], "role": r["role"], "circle": r["circle"], "kind": r["kind"],
                "weight": r["weight"], "opportunity": bool(r["opportunity"]), "sensed": r["sensed"],
                "age": age_days(r), "stale": r["status"] == "open" and age_days(r) > stale,
                "outcome": r["outcome"], "note": r["note"], "processed": r["processed"]}

    open_rows = order([r for r in rows if r["status"] == "open"])
    done = sorted([r for r in rows if r["status"] != "open"], key=lambda r: r["processed"], reverse=True)
    roles = {r: 0 for r in my_roles()}
    for r in open_rows:
        roles[r["role"]] = roles.get(r["role"], 0) + 1
    print(json.dumps({
        "now": now(), "stale_days": stale, "circle": values()["circle"],
        "counts": {"open": len(open_rows),
                   "tactical": sum(r["kind"] == "tactical" for r in open_rows),
                   "governance": sum(r["kind"] == "governance" for r in open_rows),
                   "untriaged": sum(not r["kind"] for r in open_rows),
                   "opportunities": sum(bool(r["opportunity"]) for r in open_rows),
                   "stale": sum(age_days(r) > stale for r in open_rows),
                   "processed_week": sum(r["processed"] >= week_ago for r in done)},
        "roles": [{"role": k, "open": v} for k, v in sorted(roles.items(), key=lambda kv: (-kv[1], kv[0].lower()))],
        "open": [item(r) for r in open_rows],
        "recent": [item(r) for r in done[:8]],
    }, ensure_ascii=False))


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in DEFAULTS:
        sys.exit("tensions settings set <roles|circle|stale_days> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "roles":
        value = ", ".join(dict.fromkeys(r.strip() for r in value.split(",") if r.strip()))
        keep(key, value)
        print(f"Your roles: {value}." if value else "No roles set.")
    elif key == "circle":
        keep(key, value)
        print(f"New tensions go to {value}." if value else "No default circle.")
    else:
        if value and not re.fullmatch(r"\d+", value):
            sys.exit("A number of days, like 14.")
        keep(key, value)
        print(f"A tension is waiting too long after {value or 14} days.")


def main(argv):
    cmd, rest = (argv[0].lower(), argv[1:]) if argv else ("", [])
    commands = {"add": cmd_add, "list": cmd_list, "show": cmd_show, "agenda": cmd_agenda, "triage": cmd_triage,
                "weight": cmd_weight, "edit": cmd_edit, "process": cmd_process, "reopen": cmd_reopen,
                "delete": cmd_delete, "settings": cmd_settings}
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd == "--json":
        cmd_json()
    elif cmd == "roles":
        cmd_roles()
    elif cmd in commands:
        commands[cmd](rest)
    elif re.fullmatch(r"#?\d+", cmd):
        cmd_show(argv)
    else:
        sys.exit(f"Unknown: {cmd}. See: tensions --help.")


if __name__ == "__main__":
    main(sys.argv[1:])
