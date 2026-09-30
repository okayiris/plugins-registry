#!/usr/bin/env python3
"""Your Todoist tasks: what is due, adding one by voice, and ticking one off. Through the Todoist API v1.

  todoist                               today and overdue
  todoist week                          the next seven days
  todoist add "<task>" [when]           add a task, like: todoist add "Call the plumber" tomorrow 9am
  todoist done <number or text>         tick a task off (a number from the last list)
  todoist projects                      your projects, with how many open tasks each
  todoist project <name>                the open tasks of one project
  todoist search <text>                 open tasks that hold the text
  todoist key                           is there a token in the vault
  todoist key ask                       let the owner paste the token in the vault

Add --json to todoist, week, project or search for the tasks as data, for another plugin (like planassistant).

The API token stays in the vault. Every call is made by the vault, which fills in the token as {g};
this script never sees it. The token is under Todoist, Settings, Integrations, Developer.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import date, datetime

HERE = os.path.dirname(os.path.realpath(__file__))
LAST_FILE = os.path.join(HERE, ".last.json")
API = "https://api.todoist.com/api/v1/"
ITEM = "todoist"
DOMAIN = "api.todoist.com"
AUTH = "Authorization: Bearer {g}"


AS_JSON = False


def fail(msg):
    if AS_JSON:
        print(json.dumps({"error": msg}, ensure_ascii=False))
        sys.exit(1)
    sys.exit(msg)


# --- the vault ------------------------------------------------------------------------------------

def vault_bin():
    p = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN")
    return p or shutil.which("kluis") or shutil.which("vault")


def vault_items():
    exe = vault_bin()
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    items = []
    for line in r.stdout.splitlines():
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p]
        if len(parts) >= 3 and not line.strip().startswith("de kluis"):
            items.append({"name": parts[0], "domain": parts[2].strip().lower()})
    return items


def token_item():
    items = vault_items()
    for it in items:
        if it["name"] == ITEM:
            return ITEM
    for it in items:
        if it["domain"].endswith("todoist.com"):
            return it["name"]
    return None


def vault_call(method, path, body=None):
    item = token_item()
    if not item:
        fail("There is no Todoist token in the vault yet. Say: todoist key ask. "
             "The token is in Todoist under Settings, Integrations, Developer.")
    cmd = [vault_bin(), "doe", item, method, API + path]
    if body is not None:
        cmd.append(json.dumps(body))
        cmd += ["--kop", "Content-Type: application/json"]
    cmd += ["--kop", AUTH]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        fail("Todoist did not answer in time.")
    out = r.stdout or ""
    first, _, rest = out.partition("\n")
    m = re.match(r"status\s+(\d+)", first.strip())
    if not m:
        fail((r.stderr or out).strip() or "The vault refused the call.")
    status = int(m.group(1))
    if status in (401, 403):
        fail("Todoist refused the token. Put a fresh one in the vault with: todoist key ask.")
    if status == 404:
        fail("Todoist does not know that task or project.")
    if status >= 400:
        fail(f"Todoist answered with status {status}.")
    rest = rest.strip()
    return json.loads(rest) if rest else {}


def get_all(path, **params):
    """Every page of a list endpoint."""
    out, cursor = [], None
    for _ in range(20):
        q = dict(params, limit=200)
        if cursor:
            q["cursor"] = cursor
        data = vault_call("GET", path + "?" + urllib.parse.urlencode(q))
        out += data.get("results") or []
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out


# --- showing tasks --------------------------------------------------------------------------------

def due_of(t):
    due = t.get("due") or {}
    value = due.get("datetime") or due.get("date")
    if not value:
        return None, ""
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, due.get("string", "")
    has_time = "T" in value
    if has_time and d.tzinfo:
        d = d.astimezone()
    return d, (d.strftime("%H:%M") if has_time else "")


def when_text(t):
    d, clock = due_of(t)
    if not d:
        return ""
    days = (d.date() - date.today()).days
    day = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(days)
    if day is None:
        day = d.strftime("%a %d %b") if days > 0 else f"{-days} days late"
    again = ", repeats" if (t.get("due") or {}).get("is_recurring") else ""
    return day + (f" {clock}" if clock else "") + again


def show(tasks, heading, empty):
    if AS_JSON:
        tasks.sort(key=lambda t: (due_of(t)[0].replace(tzinfo=None) if due_of(t)[0] else datetime.max, -t.get("priority", 1)))
        print(json.dumps({"tasks": [{"n": n, "id": t["id"], "content": t["content"], "priority": t.get("priority", 1),
                                     "due": (t.get("due") or {}).get("date", ""), "time": due_of(t)[1],
                                     "when": when_text(t)} for n, t in enumerate(tasks, 1)]}, ensure_ascii=False))
        with open(LAST_FILE, "w", encoding="utf-8") as f:
            json.dump([{"id": t["id"], "content": t["content"]} for t in tasks], f)
        return
    if not tasks:
        print(empty)
        return
    projects = {p["id"]: p["name"] for p in get_all("projects")}
    tasks.sort(key=lambda t: (due_of(t)[0].replace(tzinfo=None) if due_of(t)[0] else datetime.max, -t.get("priority", 1)))
    print(heading)
    for n, t in enumerate(tasks, 1):
        flag = " (urgent)" if t.get("priority") == 4 else " (high)" if t.get("priority") == 3 else ""
        where = projects.get(t.get("project_id"), "")
        extra = ", ".join(x for x in (when_text(t), where if where != "Inbox" else "") if x)
        print(f"{n:>2}. {t['content']}{flag}" + (f"  ({extra})" if extra else ""))
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump([{"id": t["id"], "content": t["content"]} for t in tasks], f)


# --- commands -------------------------------------------------------------------------------------

def cmd_today():
    tasks = get_all("tasks/filter", query="today | overdue")
    show(tasks, f"{len(tasks)} task{'s' if len(tasks) != 1 else ''} for today:", "Nothing due today.")


def cmd_week():
    tasks = get_all("tasks/filter", query="overdue | 7 days")
    show(tasks, "The next seven days:", "Nothing due in the next seven days.")


def cmd_add(args):
    if not args:
        fail('todoist add "<task>" [when]')
    content = args[0] if len(args) > 1 else " ".join(args)
    when = " ".join(args[1:]) if len(args) > 1 else ""
    body = {"content": content}
    if when:
        body["due_string"] = when
        body["due_lang"] = "en"
    t = vault_call("POST", "tasks", body)
    due = when_text(t)
    print(f"Added: {t.get('content', content)}" + (f", {due}." if due else ", no date."))


def cmd_done(args):
    text = " ".join(args).strip()
    if not text:
        fail("todoist done <number or text>")
    task = None
    if text.isdigit():
        try:
            with open(LAST_FILE, encoding="utf-8") as f:
                last = json.load(f)
        except (OSError, ValueError):
            last = []
        n = int(text)
        if not 1 <= n <= len(last):
            fail("That number is not in the last list. Ask for today's tasks first.")
        task = last[n - 1]
    else:
        hits = [t for t in get_all("tasks") if text.lower() in t["content"].lower()]
        if not hits:
            fail(f"No open task holds {text}.")
        if len(hits) > 1 and not any(t["content"].lower() == text.lower() for t in hits):
            show(hits, "Several tasks fit; say the number:", "")
            return
        task = next((t for t in hits if t["content"].lower() == text.lower()), hits[0])
    vault_call("POST", f"tasks/{task['id']}/close")
    print(f"Done: {task['content']}.")


def cmd_projects():
    projects = get_all("projects")
    counts = {}
    for t in get_all("tasks"):
        counts[t.get("project_id")] = counts.get(t.get("project_id"), 0) + 1
    print("Your projects:")
    for p in projects:
        print(f"  {p['name']}: {counts.get(p['id'], 0)} open")


def cmd_project(args):
    name = " ".join(args).strip().lower()
    projects = [p for p in get_all("projects") if name in p["name"].lower()]
    if not projects:
        fail(f"There is no project called {' '.join(args)}.")
    p = next((x for x in projects if x["name"].lower() == name), projects[0])
    tasks = get_all("tasks", project_id=p["id"])
    show(tasks, f"{p['name']}, {len(tasks)} open:", f"Nothing open in {p['name']}.")


def cmd_search(args):
    text = " ".join(args).strip().lower()
    if not text:
        fail("todoist search <text>")
    hits = [t for t in get_all("tasks") if text in t["content"].lower() or text in (t.get("description") or "").lower()]
    show(hits, f"Open tasks with {text}:", f"No open task holds {text}.")


def cmd_key(args):
    if args and args[0] == "ask":
        exe = vault_bin()
        if not exe:
            fail("The vault is not on this system.")
        print("A window opens to paste your Todoist API token; it goes straight into the vault.")
        r = subprocess.run([exe, "vraag", ITEM, "--domein", DOMAIN, "Todoist API token"],
                           capture_output=True, text=True, timeout=240)
        if r.returncode != 0:
            fail((r.stderr or r.stdout).strip() or "The vault did not save a token.")
        print((r.stdout or "").strip() or "Saved in the vault.")
        return
    item = token_item()
    print(f'A Todoist token is in the vault as "{item}".' if item else
          "No Todoist token in the vault yet. Say: todoist key ask.")


def main(argv):
    global AS_JSON
    AS_JSON = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    commands = {"week": lambda a: cmd_week(), "add": cmd_add, "done": cmd_done, "projects": lambda a: cmd_projects(),
                "project": cmd_project, "search": cmd_search, "key": cmd_key, "today": lambda a: cmd_today()}
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_today()
    elif cmd in commands:
        commands[cmd](rest)
    else:
        fail('todoist, todoist add "<task>" [when], todoist done <number>. `todoist help` shows everything.')


if __name__ == "__main__":
    main(sys.argv[1:])
