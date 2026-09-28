#!/usr/bin/env python3
"""Claude Code in this house: a coding agent that works in the owner's own projects, inside the house.

  claude-code                                   is it installed and signed in, the folder, the last runs
  claude-code ask "<question>" [--in <folder>]  a question about the code; reads, never changes anything
  claude-code do "<task>" [--in <folder>] [--shell]
                                                a task: it may change files in that folder, and with
                                                --shell (or the setting) also run commands there
  claude-code start "<task>" [--in ...] [--shell] [--read-only]
                                                the same as do, in the background; ask later with runs
  claude-code more "<text>" [<run>]             go on in the same conversation (the last run by default)
  claude-code runs                              the last runs, busy or done
  claude-code result [<run>]                    the whole answer of a run
  claude-code stop <run>                        stop a run that is still busy
  claude-code folders                           the projects in the base folder
  claude-code install | update                  put Claude Code in this plugin's folder (npm)
  claude-code login [console] | logout          sign in with a Claude plan, or a Console account
  claude-code settings [set <key> <value>]      folder, model, shell, budget, minutes

A folder is a name under the base folder (~/code by default) or a path. Claude Code keeps its own login in
this plugin's folder (.claude/); this script never reads it. Without --shell it can only read and edit
files; every other tool is refused, never asked.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG_DIR = os.path.join(HERE, ".claude")
CLI_DIR = os.path.join(HERE, ".cli")
VALUES = os.path.join(HERE, "values.json")
PACKAGE = "@anthropic-ai/claude-code"
SELF = "claude-code"

DEFAULTS = {"folder": "~/code", "model": "", "shell": "off", "budget": "2", "minutes": "20"}
TOOLS = {
    "read": ["Read", "Grep", "Glob"],
    "edit": ["Read", "Grep", "Glob", "Edit", "Write"],
    "shell": ["Read", "Grep", "Glob", "Edit", "Write", "Bash"],
}
MODE_WORDS = {"read": "read-only", "edit": "may edit files", "shell": "may edit files and run commands"}
BRIEF = ("You work for the owner of this Iris house, inside the house's own workspace. Iris reads your final "
         "answer back to them, often out loud: keep it short and plain, say what you found or changed and in "
         "which files, and what is left to do. No tables, no long code blocks.")
SHOWN = 1500


def fail(msg):
    sys.exit(msg)


# --- settings ---------------------------------------------------------------------------------------

def values():
    try:
        with open(VALUES, encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_values(v):
    with open(VALUES + ".tmp", "w", encoding="utf-8") as f:
        json.dump({k: v[k] for k in DEFAULTS if k in v}, f, indent=1)
    os.replace(VALUES + ".tmp", VALUES)


def number(text, lo, hi):
    try:
        n = float(str(text).replace(",", "."))
    except ValueError:
        return None
    return n if lo <= n <= hi else None


def cmd_settings(args):
    v = values()
    if not args:
        print(json.dumps({k: v[k] for k in DEFAULTS}, ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in DEFAULTS:
        fail(f"{SELF} settings set <{'|'.join(DEFAULTS)}> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "folder":
        value = value or DEFAULTS["folder"]
        v[key] = value
        save_values(v)
        print(f"Projects live in {value}.")
    elif key == "model":
        if value and not re.fullmatch(r"[a-z0-9.\-\[\]]+", value):
            fail("A model is a name like sonnet, opus or claude-sonnet-5; empty is Claude Code's own choice.")
        v[key] = value
        save_values(v)
        print(f"Model: {value}." if value else "Model: Claude Code's own choice.")
    elif key == "shell":
        if value not in ("on", "off"):
            fail("shell is on or off.")
        v[key] = value
        save_values(v)
        print("Tasks may also run commands in their folder." if value == "on"
              else "Tasks only read and edit files, unless you add --shell.")
    elif key == "budget":
        if number(value, 0.1, 100) is None:
            fail("The budget is an amount in dollars per run, between 0.1 and 100.")
        v[key] = value
        save_values(v)
        print(f"At most ${value} per run.")
    elif key == "minutes":
        if number(value, 1, 240) is None:
            fail("Minutes is how long a run may take in the foreground, between 1 and 240.")
        v[key] = value
        save_values(v)
        print(f"A run in the foreground stops after {value} minutes; start runs in the background.")


# --- Claude Code itself -----------------------------------------------------------------------------

def claude_bin():
    own = os.path.join(CLI_DIR, "node_modules", ".bin", "claude")
    for exe in (os.environ.get("CLAUDE_CODE_BIN"), shutil.which("claude"), own):
        if exe and os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
    return None


def claude_env():
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = CONFIG_DIR
    env["DISABLE_AUTOUPDATER"] = "1"
    env["CLAUDE_CODE_ENTRYPOINT"] = "iris-plugin"
    return env


def need_claude():
    exe = claude_bin()
    if not exe:
        fail(f"Claude Code is not installed in this house yet. Say: {SELF} install.")
    return exe


def version(exe):
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, env=claude_env())
    except (OSError, subprocess.SubprocessError):
        return ""
    return (r.stdout.strip().split() or [""])[0]


def auth(exe):
    try:
        r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=30,
                           env=claude_env())
        return json.loads(r.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


def signed_in(exe):
    return bool(auth(exe).get("loggedIn")) or bool(os.environ.get("ANTHROPIC_API_KEY"))


def cmd_install(update=False):
    npm = shutil.which("npm")
    if not npm:
        fail("There is no npm in this house, and Claude Code comes from npm.")
    os.makedirs(CLI_DIR, exist_ok=True)
    try:
        r = subprocess.run([npm, "install", "--prefix", CLI_DIR, "--no-audit", "--no-fund", "--loglevel=error",
                            PACKAGE + "@latest"], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        fail("Installing took longer than ten minutes; try again later.")
    if r.returncode != 0:
        fail("npm could not install Claude Code: " + ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1])
    exe = os.path.join(CLI_DIR, "node_modules", ".bin", "claude")
    v = version(exe)
    print(f"Claude Code {v} is {'updated' if update else 'installed'} in this house." if v
          else "Claude Code is installed.")
    if claude_bin() != exe:
        print(f"There is also a claude on the path ({claude_bin()}); that one is used first.")
    if not signed_in(exe):
        print(f"Next: sign in once. In the house's terminal, type: {SELF} login")


def cmd_login(args):
    exe = need_claude()
    how = ["--console"] if args[:1] == ["console"] else []
    if not sys.stdin.isatty():
        print("Signing in happens once, in the house's own terminal, because it opens a page to confirm on. "
              f"Ask the owner to open the terminal and type: {SELF} login"
              + (" console" if how else "")
              + ". With a Claude plan (Pro or Max) that is all; with an Anthropic Console account add console.")
        return
    os.execve(exe, [exe, "auth", "login", *how], claude_env())


def cmd_logout():
    exe = need_claude()
    subprocess.run([exe, "auth", "logout"], env=claude_env(), capture_output=True, text=True, timeout=60)
    print("Claude Code is signed out in this house.")


# --- folders ----------------------------------------------------------------------------------------

def base_folder():
    return os.path.realpath(os.path.expanduser(values()["folder"]))


def folder_of(name, create=False):
    name = (name or "").strip()
    if not name:
        path = base_folder()
    elif name.startswith(("/", "~")):
        path = os.path.realpath(os.path.expanduser(name))
    else:
        if not re.fullmatch(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*", name) or ".." in name.split("/"):
            fail(f"{name} is not a folder name; use a name under {values()['folder']} or a whole path.")
        path = os.path.join(base_folder(), name)
    if path in ("/", os.path.realpath(os.path.expanduser("~"))) or path.startswith(HERE):
        fail("Pick a project folder, not the whole house or this plugin's own folder.")
    if not os.path.isdir(path):
        if not create:
            fail(f"There is no folder {path}. Say {SELF} folders to see the projects.")
        os.makedirs(path, exist_ok=True)
    return path


def short_path(path):
    home = os.path.realpath(os.path.expanduser("~"))
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def cmd_folders():
    base = base_folder()
    if not os.path.isdir(base):
        print(f"{short_path(base)} does not exist yet. A task with --in <name> makes the folder.")
        return
    names = sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)) and not n.startswith("."))
    if not names:
        print(f"No projects in {short_path(base)} yet.")
        return
    print(f"{len(names)} project{'s' if len(names) != 1 else ''} in {short_path(base)}:")
    for n in names:
        git = " (git)" if os.path.isdir(os.path.join(base, n, ".git")) else ""
        print(f"  {n}{git}")


# --- runs -------------------------------------------------------------------------------------------

def run_path(n):
    return os.path.join(HERE, f".run-{n}.json")


def load_run(n):
    try:
        with open(run_path(n), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_run(run):
    path = run_path(run["n"])
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def run_numbers():
    found = []
    for f in os.listdir(HERE):
        m = re.fullmatch(r"\.run-(\d+)\.json", f)
        if m:
            found.append(int(m.group(1)))
    return sorted(found)


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            return f.read().split(") ")[-1][:1] != "Z"
    except OSError:
        return True


def state(run):
    if run.get("status") == "busy" and not alive(run.get("pid")):
        run["status"] = "lost"
        save_run(run)
    return run.get("status")


def pick_run(arg):
    nums = run_numbers()
    if not nums:
        fail(f"There are no runs yet. Start one with {SELF} ask or {SELF} do.")
    if arg in (None, "", "last"):
        return load_run(nums[-1])
    if not str(arg).isdigit() or int(arg) not in nums:
        fail(f"There is no run {arg}. Say {SELF} runs to see them.")
    return load_run(int(arg))


def ago(ts):
    s = max(0, int(time.time() - ts))
    if s < 90:
        return f"{s}s ago"
    if s < 5400:
        return f"{s // 60} min ago"
    if s < 172800:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


def took(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60}m {seconds % 60}s" if seconds >= 60 else f"{seconds}s"


def clip(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


# --- running Claude Code ----------------------------------------------------------------------------

def command_line(exe, run):
    v = values()
    tools = TOOLS[run["mode"]]
    cmd = [exe, "-p", run["task"], "--output-format", "json", "--permission-mode", "dontAsk",
           "--tools", ",".join(tools), "--allowedTools", *tools, "--append-system-prompt", BRIEF]
    budget = number(v["budget"], 0.1, 100)
    if budget:
        cmd += ["--max-budget-usd", f"{budget:g}"]
    if v["model"]:
        cmd += ["--model", v["model"]]
    if run.get("resume"):
        cmd += ["--resume", run["resume"]]
    return cmd


def finish(run, code, out, err):
    """Read Claude Code's one JSON answer into the run."""
    data = None
    for line in reversed((out or "").strip().splitlines()):
        try:
            data = json.loads(line)
            break
        except ValueError:
            continue
    if data is None:
        try:
            data = json.loads(out)
        except ValueError:
            data = {}
    run["ended"] = time.time()
    run["session"] = data.get("session_id") or run.get("session") or run.get("resume")
    run["cost"] = data.get("total_cost_usd")
    run["turns"] = data.get("num_turns")
    run["denied"] = sorted({d.get("tool_name", "?") for d in data.get("permission_denials") or []})
    if data.get("result") is not None and not data.get("is_error"):
        run["status"], run["answer"] = "done", str(data["result"]).strip()
    else:
        problem = data.get("result") or data.get("error") or (err or out or "").strip()
        if data.get("subtype") == "error_max_budget_usd":
            problem = f"It stopped at the budget of ${values()['budget']} for one run."
        elif data.get("subtype") == "error_max_turns":
            problem = "It stopped after too many turns."
        run["status"], run["answer"] = "failed", explain(str(problem), code)
    save_run(run)
    return run


def explain(problem, code):
    low = problem.lower()
    if any(w in low for w in ("not logged in", "please run /login", "invalid api key", "authentication",
                              "oauth token", "401")):
        return f"Claude Code is not signed in. In the house's terminal, type: {SELF} login"
    lines = [l for l in problem.strip().splitlines() if l.strip()]
    return clip(lines[-1] if lines else f"Claude Code stopped with code {code}.", 400)


def execute(run, timeout=None):
    exe = need_claude()
    try:
        p = subprocess.run(command_line(exe, run), cwd=run["folder"], env=claude_env(), capture_output=True,
                           text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return finish(run, p.returncode, p.stdout, p.stderr)
    except subprocess.TimeoutExpired:
        run.update(status="failed", ended=time.time(),
                   answer=f"Still busy after {took(timeout)}, so it was stopped. Long tasks go in the background: "
                          f"{SELF} start.")
        save_run(run)
        return run


def new_run(task, folder, mode, resume=None, parent=None):
    nums = run_numbers()
    run = {"n": (nums[-1] + 1) if nums else 1, "task": task, "folder": folder, "mode": mode, "status": "busy",
           "started": time.time(), "resume": resume, "parent": parent, "pid": os.getpid()}
    save_run(run)
    for old in nums[:-49]:  # keep the last fifty
        try:
            os.remove(run_path(old))
        except OSError:
            pass
    return run


def report(run, full=False):
    head = f"Run {run['n']} in {short_path(run['folder'])} ({MODE_WORDS[run['mode']]})"
    status = state(run)
    if status == "busy":
        print(f"{head}: still busy, started {ago(run['started'])}.")
        return
    if status == "lost":
        print(f"{head}: stopped before it finished.")
        return
    answer = run.get("answer") or ""
    if status == "failed":
        print(f"{head} did not finish. {answer}")
    else:
        if not full and len(answer) > SHOWN:
            cut = answer[:SHOWN].rsplit("\n", 1)[0].rstrip()
            answer = cut + f"\n\n(The answer goes on; {SELF} result {run['n']} shows all of it.)"
        print(answer or "Done, without an answer.")
    facts = [took(run.get("ended", run["started"]) - run["started"])]
    if run.get("turns"):
        facts.append(f"{run['turns']} turns")
    if run.get("cost"):
        facts.append(f"about ${run['cost']:.2f}")
    print(f"\n({head}: {', '.join(facts)}.)")
    denied = [t for t in run.get("denied") or [] if t not in TOOLS[run["mode"]]]
    if denied:
        wanted = " and ".join(denied)
        hint = (f"{SELF} more \"go on\" {run['n']} --shell" if "Bash" in denied and run["mode"] != "shell"
                else f"{SELF} more \"go on\" {run['n']} --edit" if run["mode"] == "read" else "")
        print(f"It was not allowed to use {wanted}." + (f" To allow it: {hint}" if hint else ""))


def parse(args, allow_read_only=False):
    folder, shell, read_only, words = None, False, False, []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--in", "--folder", "-C") and i + 1 < len(args):
            folder = args[i + 1]
            i += 2
            continue
        if a == "--shell":
            shell = True
        elif a in ("--read-only", "--ask") and allow_read_only:
            read_only = True
        else:
            words.append(a)
        i += 1
    return folder, shell, read_only, " ".join(words).strip()


def minutes():
    return (number(values()["minutes"], 1, 240) or 20) * 60


def edit_mode(shell):
    return "shell" if shell or values()["shell"] == "on" else "edit"


def need_ready(exe):
    if not signed_in(exe):
        fail(f"Claude Code is not signed in yet. In the house's terminal, type: {SELF} login")


def cmd_ask(args):
    folder, _, _, task = parse(args)
    if not task:
        fail(f'{SELF} ask "<question>" [--in <folder>]')
    exe = need_claude()
    need_ready(exe)
    run = new_run(task, folder_of(folder), "read")
    report(execute(run, timeout=minutes()))


def cmd_do(args):
    folder, shell, _, task = parse(args)
    if not task:
        fail(f'{SELF} do "<task>" [--in <folder>] [--shell]')
    exe = need_claude()
    need_ready(exe)
    run = new_run(task, folder_of(folder, create=True), edit_mode(shell))
    report(execute(run, timeout=minutes()))


def cmd_start(args):
    folder, shell, read_only, task = parse(args, allow_read_only=True)
    if not task:
        fail(f'{SELF} start "<task>" [--in <folder>] [--shell] [--read-only]')
    exe = need_claude()
    need_ready(exe)
    mode = "read" if read_only else edit_mode(shell)
    run = new_run(task, folder_of(folder, create=not read_only), mode)
    background(run)


def background(run):
    p = subprocess.Popen([sys.executable, os.path.realpath(__file__), "_work", str(run["n"])],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, cwd=run["folder"])
    run["pid"] = p.pid
    save_run(run)
    print(f"Run {run['n']} started in {short_path(run['folder'])} ({MODE_WORDS[run['mode']]}). "
          f"Ask later with {SELF} runs, or {SELF} result {run['n']}.")


def cmd_work(args):
    run = load_run(int(args[0])) if args and args[0].isdigit() else None
    if run:
        run["pid"] = os.getpid()
        save_run(run)
        execute(run)


def cmd_more(args):
    _, shell, _, rest = parse(args)
    edit = "--edit" in rest.split()
    words = [w for w in rest.split() if w != "--edit"]
    target = None
    if len(words) > 1 and words[-1].isdigit():
        target = words.pop()
    text = " ".join(words).strip()
    if not text:
        fail(f'{SELF} more "<text>" [<run>]')
    prev = pick_run(target)
    if state(prev) == "busy":
        fail(f"Run {prev['n']} is still busy; wait for it, or {SELF} stop {prev['n']}.")
    if not prev.get("session"):
        fail(f"Run {prev['n']} has no conversation to go on with; start a new one.")
    if not os.path.isdir(prev["folder"]):
        fail(f"The folder {prev['folder']} is gone.")
    mode = prev["mode"]
    if shell:
        mode = "shell"
    elif edit and mode == "read":
        mode = edit_mode(False)
    exe = need_claude()
    need_ready(exe)
    run = new_run(text, prev["folder"], mode, resume=prev["session"], parent=prev["n"])
    report(execute(run, timeout=minutes()))


def cmd_runs():
    nums = run_numbers()
    if not nums:
        print(f"No runs yet. Try: {SELF} ask \"what does this project do?\" --in <folder>")
        return
    print("The last runs:")
    for n in reversed(nums[-10:]):
        run = load_run(n)
        if not run:
            continue
        status = state(run)
        word = {"busy": "busy", "done": "done", "failed": "did not finish", "lost": "stopped"}.get(status, status)
        folder = os.path.basename(run["folder"]) or run["folder"]
        print(f"{n:>3}. {word}, {ago(run['started'])}, {folder}: {clip(run['task'], 70)}")


def cmd_result(args):
    report(pick_run(args[0] if args else None), full=True)


def cmd_stop(args):
    if not args:
        fail(f"{SELF} stop <run>")
    run = pick_run(args[0])
    if state(run) != "busy":
        print(f"Run {run['n']} is not busy.")
        return
    try:
        os.killpg(os.getpgid(run["pid"]), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    run.update(status="failed", ended=time.time(), answer="Stopped on request.")
    save_run(run)
    print(f"Run {run['n']} is stopped. What it already changed in {short_path(run['folder'])} stays.")


def cmd_status():
    exe = claude_bin()
    if not exe:
        print(f"Claude Code is not installed in this house yet. Say: {SELF} install")
        return
    v = version(exe)
    a = auth(exe)
    line = f"Claude Code {v}".strip() + " is installed"
    if a.get("loggedIn"):
        how = {"claude.ai": "with a Claude plan", "oauth_token": "with a Claude plan",
               "console": "with a Console account", "api_key": "with an API key"}.get(a.get("authMethod"), "")
        line += f" and signed in {how}".rstrip() + "."
    elif os.environ.get("ANTHROPIC_API_KEY"):
        line += ", with the house's API key."
    else:
        line += f", but not signed in. In the house's terminal, type: {SELF} login"
    print(line)
    v = values()
    print(f"Projects: {short_path(base_folder())}. Tasks {'may' if v['shell'] == 'on' else 'only with --shell'} "
          f"run commands; at most ${v['budget']} per run.")
    nums = run_numbers()
    if nums:
        run = load_run(nums[-1])
        if run:
            print(f"Last run {run['n']} ({state(run)}, {ago(run['started'])}): {clip(run['task'], 70)}")


def main(argv):
    if argv[:1] in (["--help"], ["-h"], ["help"]):
        print(__doc__.strip())
        return
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    table = {
        "": lambda: cmd_status(), "status": lambda: cmd_status(),
        "ask": lambda: cmd_ask(rest), "do": lambda: cmd_do(rest), "start": lambda: cmd_start(rest),
        "more": lambda: cmd_more(rest), "runs": lambda: cmd_runs(), "result": lambda: cmd_result(rest),
        "stop": lambda: cmd_stop(rest), "folders": lambda: cmd_folders(),
        "install": lambda: cmd_install(), "update": lambda: cmd_install(update=True),
        "login": lambda: cmd_login(rest), "logout": lambda: cmd_logout(),
        "settings": lambda: cmd_settings(rest), "_work": lambda: cmd_work(rest),
    }
    if cmd not in table:
        fail(f"{SELF} does not know {cmd}. Say {SELF} --help.")
    table[cmd]()


if __name__ == "__main__":
    main(sys.argv[1:])
