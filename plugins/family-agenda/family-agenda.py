#!/usr/bin/env python3
"""The family agenda, in a few lines. Iris reads the Google agenda of this house.

  family-agenda                                  today and tomorrow
  family-agenda week                             the next seven days
  family-agenda zoek <tekst>                     search on title or place
  family-agenda plan "<titel>" <datum> <tijd>    put something in the agenda
          [--wie naam] [--waar plaats] [--proef]
  family-agenda lid <naam> [e-mail]              remember a family member
  family-agenda lid                              show the family members
  family-agenda lid weg <naam>                   forget a family member

Planning goes through `google cal add`, so the owner approves it on screen before it is placed.
Without a link to Google this command says so and stops; nothing else changes.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
SETTINGS = os.path.join(HERE, "settings.json")

DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


# --- helpers ---------------------------------------------------------------------------------

def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def google():
    found = shutil.which("google")
    if found:
        return found
    for path in ("/usr/local/bin/google", "/opt/agi/bin/google"):
        if os.path.exists(path):
            return path
    return None


def run_google(args):
    exe = google()
    if not exe:
        return 127, "", "the google command is not on this system"
    try:
        r = subprocess.run([exe] + args, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return 124, "", "Google did not answer in time"
    return r.returncode, r.stdout, r.stderr


def calendar(days, from_date=None, query=None):
    """Read the agenda. Returns (timezone, events) or raises SystemExit with a neat message."""
    args = ["cal", "list", str(days)]
    if from_date:
        args += ["--from", from_date]
    if query:
        args += ["--q", query]
    rc, out, err = run_google(args)
    if rc != 0:
        sys.exit(f"family-agenda: {err.strip() or 'Google is not linked yet'}\n"
                 "Link Google on the Integrations screen, then try again.")
    try:
        data = json.loads(out)
    except ValueError:
        sys.exit("family-agenda: Google did not return an agenda. Link Google on the Integrations screen.")
    events = data.get("events") or []
    return data.get("timeZone") or os.environ.get("TZ") or "Europe/Amsterdam", events


def now_in(tzname):
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tzname))
    except Exception:
        try:
            os.environ["TZ"] = tzname
            time.tzset()
        except Exception:
            pass
        return datetime.now()


def nl_date(d):
    return f"{DAGEN[d.weekday()]} {d.day} {MAANDEN[d.month - 1]}"


def day_name(d, today):
    if d == today:
        return "Vandaag"
    if d == today + timedelta(days=1):
        return "Morgen"
    return nl_date(d)


def clock(ev):
    start = str(ev.get("start") or "")
    if "T" in start:
        return start[11:16]
    return "hele dag"


def guests(ev):
    names = []
    for addr in ev.get("with") or []:
        addr = str(addr)
        if addr.endswith("@woodst.nl"):
            continue
        names.append(addr.split("@")[0])
    if not names:
        return ""
    if len(names) <= 3:
        return "met " + ", ".join(names)
    return f"met {names[0]} en {len(names) - 1} anderen"


def line(ev):
    bits = [clock(ev), str(ev.get("title") or "(zonder titel)")]
    where = (ev.get("where") or "").split(",")[0].strip()
    if where:
        bits.append(f"({where})")
    who = guests(ev)
    if who:
        bits.append(who)
    return "  ".join(bits)


def show(events, days, today):
    """Print the events per day for the given window, only the days that matter."""
    by_date = {}
    for ev in events:
        start = str(ev.get("start") or "")
        by_date.setdefault(start[:10], []).append(ev)
    shown = 0
    for i in range(days):
        d = today + timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        if d == today or d == today + timedelta(days=1):
            head = day_name(d, today)
        else:
            head = nl_date(d)
        print(head)
        day_events = sorted(by_date.get(key, []), key=lambda e: str(e.get("start") or ""))
        if day_events:
            for ev in day_events:
                print("  " + line(ev))
                shown += 1
        else:
            print("  geen afspraken")
        print()
    return shown


# --- commands --------------------------------------------------------------------------------

def cmd_vandaag():
    tz, events = calendar(3)
    today = now_in(tz).date()
    show(events, 2, today)


def cmd_week():
    tz, events = calendar(8)
    today = now_in(tz).date()
    show(events, 7, today)


def cmd_zoek(args):
    term = " ".join(args[1:]).strip()
    if not term:
        sys.exit("family-agenda zoek: give a word to search for")
    tz, events = calendar(90)
    today = now_in(tz).date()
    needle = term.lower()
    hits = [ev for ev in events
            if needle in str(ev.get("title") or "").lower()
            or needle in str(ev.get("where") or "").lower()]
    if not hits:
        print(f"Niets gevonden voor \u201c{term}\u201d in de komende drie maanden.")
        return
    for ev in sorted(hits, key=lambda e: str(e.get("start") or "")):
        start = str(ev.get("start") or "")
        try:
            d = datetime.strptime(start[:10], "%Y-%m-%d").date()
            prefix = day_name(d, today)
        except ValueError:
            prefix = start[:10]
        print(f"{prefix:<8} {line(ev)}")
    print(f"{len(hits)} afspraak(en) gevonden.")


def find_email(name, members):
    name = name.strip().lower()
    if "@" in name:
        return name
    for m in members:
        if str(m.get("name", "")).lower() == name:
            return m.get("email") or None
    return None


def cmd_plan(args):
    rest = args[1:]
    proef = "--proef" in rest
    rest = [a for a in rest if a != "--proef"]
    wie = waar = None
    words = []
    i = 0
    while i < len(rest):
        if rest[i] == "--wie" and i + 1 < len(rest):
            wie = rest[i + 1]
            i += 2
        elif rest[i] == "--waar" and i + 1 < len(rest):
            waar = rest[i + 1]
            i += 2
        else:
            words.append(rest[i])
            i += 1
    if len(words) < 3:
        sys.exit('family-agenda plan "<titel>" <datum> <tijd> [--wie naam] [--waar plaats]')
    titel, datum, tijd = words[0], words[1], words[2]
    try:
        start = datetime.strptime(f"{datum} {tijd}", "%Y-%m-%d %H:%M")
    except ValueError:
        sys.exit("family-agenda plan: use a date like 2026-10-01 and a time like 16:30")
    end = start + timedelta(hours=1)
    start_s = start.strftime("%Y-%m-%dT%H:%M")
    end_s = end.strftime("%Y-%m-%dT%H:%M")

    note = None
    email = find_email(wie, load_settings().get("members") or []) if wie else None
    if wie and not email:
        note = f"Wie: {wie}"
    cmd = ["google", "cal", "add", titel, start_s, end_s]
    if waar:
        cmd += ["--where", waar]
    if email:
        cmd += ["--with", email]
    if note:
        cmd += ["--note", note]

    if proef:
        print("Zou uitvoeren: " + " ".join(shlex.quote(c) for c in cmd))
        return
    rc, out, err = run_google(cmd[1:])
    if rc != 0:
        sys.exit(f"family-agenda: {(err or out).strip() or 'adding did not work'}")
    print(f"In de agenda: {titel}, {nl_date(start.date())} {start.strftime('%H:%M')}.")
    if where := waar:
        print(f"  waar: {where}")
    if wie:
        print(f"  wie: {wie}" + (f" ({email})" if email else " (in de notitie)"))
    print("De eigenaar zag het verzoek en heeft het goedgekeurd.")


def cmd_lid(args):
    members = list(load_settings().get("members") or [])
    rest = args[1:]
    if not rest:
        if not members:
            print("Nog geen familieleden bekend. Voeg er een toe met `family-agenda lid <naam>`.")
            return
        for m in members:
            print(f"{m.get('name')}" + (f"  {m.get('email')}" if m.get("email") else ""))
        return
    if rest[0] == "weg":
        if len(rest) < 2:
            sys.exit("family-agenda lid weg <naam>")
        naam = rest[1].lower()
        members = [m for m in members if str(m.get("name", "")).lower() != naam]
        save_settings(load_settings() | {"members": members})
        print(f"{rest[1]} is vergeten.")
        return
    naam = rest[0]
    email = rest[1] if len(rest) > 1 else None
    new = {"name": naam}
    if email:
        new["email"] = email
    members = [m for m in members if str(m.get("name", "")).lower() != naam.lower()]
    members.append(new)
    save_settings(load_settings() | {"members": members})
    print(f"{naam} onthouden." + (f" Plant met {naam} via {email}." if email else
          f" Zonder e-mail komt {naam} in de notitie; geef een adres mee voor een uitnodiging."))


def main():
    args = sys.argv[1:]
    if not args:
        cmd_vandaag()
    elif args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif args[0] in ("vandaag", "today"):
        cmd_vandaag()
    elif args[0] in ("week", "7"):
        cmd_week()
    elif args[0] == "zoek":
        cmd_zoek(args)
    elif args[0] == "plan":
        cmd_plan(args)
    elif args[0] == "lid":
        cmd_lid(args)
    else:
        print(f"family-agenda: onbekend commando \u201c{args[0]}\u201d\n")
        print(__doc__.strip())


if __name__ == "__main__":
    main()
