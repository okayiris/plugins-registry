#!/usr/bin/env python3
"""A test environment for Iris plugins: a simulated home, recorded internet, a stand-in vault, screens.

  python3 testenv/sim.py test [plugin...]            run the scenarios (testenv/scenarios/<plugin>.json)
  python3 testenv/sim.py test weather --record       run them against the internet and record the answers
  python3 testenv/sim.py smoke [plugin...]           every command of every plugin: help, and no arguments;
                                                     nothing may crash, offline and with an empty vault
  python3 testenv/sim.py run <plugin> [--live] -- <command line>
                                                     one command in a lasting home (testenv/.home)
  python3 testenv/sim.py screen [plugin...]          draw windows and screens, screenshots in testenv/out
  python3 testenv/sim.py serve <plugin>              draw one screen and keep it open on http://127.0.0.1:8765

What the plugin sees is an Iris home: its folder in ~/plugins/<name>/, its commands on the path, data.db
made from schema.sql when it asks for a database, and `kluis` / `vault` for keys. Internet calls are
answered from testenv/cassettes/<plugin>.json (see runtime/sitecustomize.py); `--record` fills that
file from the real internet, `--live` uses the internet without keeping anything. Keys for a live or
recording run come from IRIS_KEY_<ITEM> (IRIS_KEY_TODOIST, IRIS_KEY_DEEPL, IRIS_KEY_NS): they are used
in the call and never written down.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.join(ROOT, "plugins")
RUNTIME = os.path.join(HERE, "runtime")
SCENARIOS = os.path.join(HERE, "scenarios")
CASSETTES = os.path.join(HERE, "cassettes")
OUT = os.path.join(HERE, "out")
LASTING = os.path.join(HERE, ".home")
DEFAULT_NOW = "2026-09-28T10:00:00"
TZ = "Europe/Amsterdam"

GREEN, RED, DIM, END = ("\033[32m", "\033[31m", "\033[2m", "\033[0m") if sys.stdout.isatty() else ("", "", "", "")


# --- a home -----------------------------------------------------------------------------------------

class Home:
    """One plugin, installed and enabled in a home of its own."""

    def __init__(self, plugin, root=None, mode="replay", now=DEFAULT_NOW, vault="", stub=None, programs=None):
        self.plugin = plugin
        self.programs = programs or {}
        self.root = root or tempfile.mkdtemp(prefix=f"iris-{plugin}-")
        self.mode = mode
        self.now = now
        self.vault = vault
        self.stub = os.path.join(HERE, stub) if stub else None
        self.bin = os.path.join(self.root, ".sim-bin")
        self.folder = os.path.join(self.root, "plugins", plugin)
        self.misses = os.path.join(self.root, ".sim-misses")
        self.vault_log = os.path.join(self.root, ".sim-vault-log")
        self.manifest = json.load(open(os.path.join(PLUGINS, plugin, "plugin.json"), encoding="utf-8"))
        self.install()

    def install(self):
        """Like `plugin install` + `plugin enable`: the folder, the commands on the path, the database."""
        os.makedirs(os.path.dirname(self.folder), exist_ok=True)
        if not os.path.exists(self.folder):
            shutil.copytree(os.path.join(PLUGINS, self.plugin), self.folder,
                            ignore=shutil.ignore_patterns("values.json", "data.db*", ".*", "__pycache__"))
        else:  # a lasting home: new code, same data
            for f in os.listdir(os.path.join(PLUGINS, self.plugin)):
                src = os.path.join(PLUGINS, self.plugin, f)
                if os.path.isfile(src) and not f.startswith(".") and f not in ("values.json",) and not f.startswith("data.db"):
                    shutil.copy2(src, os.path.join(self.folder, f))
        os.makedirs(self.bin, exist_ok=True)
        for cmd, file in (self.manifest.get("commands") or {}).items():
            self.wrap(cmd, os.path.join(self.folder, file))
        for name in ("kluis", "vault"):
            self.wrap(name, os.path.join(RUNTIME, "vault.py"))
        for name, stub in self.programs.items():  # a program the house has, like the claude CLI
            self.wrap(name, os.path.join(HERE, stub))
        schema = os.path.join(self.folder, "schema.sql")
        db = os.path.join(self.folder, "data.db")
        if self.manifest.get("database") and os.path.exists(schema) and not os.path.exists(db):
            con = sqlite3.connect(db)
            con.executescript(open(schema, encoding="utf-8").read())
            con.close()

    def wrap(self, name, target):
        """The marketplace keeps no executable bit, so the house runs a command through its #! line."""
        first = open(target, encoding="utf-8", errors="replace").readline().strip()
        interp = first[2:].strip() if first.startswith("#!") else "python3"
        path = os.path.join(self.bin, name)
        with open(path, "w") as f:
            f.write(f"#!/bin/sh\nexec {interp} {shlex.quote(target)} \"$@\"\n")
        os.chmod(path, 0o755)

    def env(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("KLUIS_", "VAULT_"))}
        env.update({
            "HOME": self.root, "PATH": self.bin + os.pathsep + env.get("PATH", ""),
            "PYTHONPATH": RUNTIME, "PYTHONDONTWRITEBYTECODE": "1", "TZ": TZ, "LANG": "C.UTF-8",
            "SIM_HTTP": self.mode, "SIM_CASSETTE": os.path.join(CASSETTES, f"{self.plugin}.json"),
            "SIM_MISSES": self.misses, "SIM_VAULT": self.vault, "SIM_VAULT_LOG": self.vault_log,
        })
        if self.now:
            env["SIM_NOW"] = self.now
        if self.stub:
            env["SIM_VAULT_STUB"] = self.stub
        return env

    def run(self, line, timeout=120, stdin=None, env=None):
        args = shlex.split(line) if isinstance(line, str) else list(line)
        try:
            p = subprocess.run(args, cwd=self.root, env={**self.env(), **(env or {})}, capture_output=True, text=True,
                               timeout=timeout, input=stdin)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, "", f"timed out after {timeout}s"
        except FileNotFoundError:
            return 127, "", f"no command {args[0]} in this home"

    def take_misses(self):
        if not os.path.exists(self.misses):
            return []
        lines = [l.strip() for l in open(self.misses, encoding="utf-8") if l.strip()]
        os.remove(self.misses)
        return lines

    def vault_calls(self):
        if not os.path.exists(self.vault_log):
            return []
        return [json.loads(l) for l in open(self.vault_log, encoding="utf-8") if l.strip()]

    def remove(self):
        shutil.rmtree(self.root, ignore_errors=True)


# --- checking an answer -----------------------------------------------------------------------------

def dig(data, path):
    for part in str(path).split("."):
        if part == "":
            continue
        if isinstance(data, list):
            if part == "length":
                return len(data)
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data[part]
        else:
            raise KeyError(path)
    return data


def check(expect, code, out, err, home):
    """Everything wrong with one step, as sentences. An empty list is a pass."""
    wrong = []
    want = expect.get("code", 0)
    if want is not None and code != want:
        wrong.append(f"exit code {code}, wanted {want}")
    if "Traceback (most recent call last)" in err or "Traceback (most recent call last)" in out:
        wrong.append("a Python traceback: " + (err or out).strip().splitlines()[-1])
    text = out + err
    for s in expect.get("contains", []):
        if s not in text:
            wrong.append(f"does not say {s!r}")
    for s in expect.get("not_contains", []):
        if s in text:
            wrong.append(f"says {s!r}, and should not")
    for r in expect.get("matches", []):
        if not re.search(r, text, re.M):
            wrong.append(f"does not match /{r}/")
    if "lines" in expect:
        n = len([l for l in out.splitlines() if l.strip()])
        lo, hi = expect["lines"] if isinstance(expect["lines"], list) else (expect["lines"], expect["lines"])
        if not lo <= n <= hi:
            wrong.append(f"{n} lines, wanted {lo} to {hi}")
    if "json" in expect:
        try:
            data = json.loads(out)
        except ValueError:
            wrong.append("the output is not JSON")
            data = None
        if data is not None:
            for path, rule in expect["json"].items():
                try:
                    value = dig(data, path)
                except (KeyError, IndexError, ValueError, TypeError):
                    wrong.append(f"no {path} in the JSON")
                    continue
                if isinstance(rule, dict):
                    if "min" in rule and not value >= rule["min"]:
                        wrong.append(f"{path} is {value}, wanted at least {rule['min']}")
                    if "contains" in rule and rule["contains"] not in str(value):
                        wrong.append(f"{path} is {value!r}, wanted it to hold {rule['contains']!r}")
                    if rule.get("present") and value in (None, "", [], {}):
                        wrong.append(f"{path} is empty")
                elif value != rule:
                    wrong.append(f"{path} is {value!r}, wanted {rule!r}")
    if "vault" in expect:
        calls = home.vault_calls()
        for needle in expect["vault"]:
            if not any(all(n in " ".join(c) for n in needle) for c in calls):
                wrong.append(f"no vault call with {needle}")
        for c in calls:
            if any(re.search(r"(?i)(bearer|key|token)[: ]+[A-Za-z0-9_-]{16,}", a) for a in c):
                wrong.append("a vault call carries what looks like a key instead of {g}")
    return wrong


# --- scenarios --------------------------------------------------------------------------------------

def scenario_names(wanted):
    have = sorted(f[:-5] for f in os.listdir(SCENARIOS) if f.endswith(".json"))
    if not wanted:
        return have
    missing = [w for w in wanted if w not in have]
    if missing:
        sys.exit(f"no scenario for {', '.join(missing)} in testenv/scenarios")
    return wanted


def load_scenario(name):
    with open(os.path.join(SCENARIOS, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def vault_items(sc):
    return ", ".join(sc.get("vault", []))


def fill(text, saved):
    """${name} in a step becomes a value saved from an earlier answer (like an order's token)."""
    return re.sub(r"\$\{(\w+)\}", lambda m: saved.get(m.group(1), m.group(0)), text)


def run_scenario(name, mode, verbose, pause=0):
    sc = load_scenario(name)
    plugin = sc.get("plugin", name)
    home = Home(plugin, mode=mode, now=sc.get("now", DEFAULT_NOW), vault=vault_items(sc), stub=sc.get("stub"),
                programs=sc.get("programs"))
    failures, steps, saved = [], sc.get("steps", []), {}
    try:
        for i, step in enumerate(steps, 1):
            if mode != "replay" and step.get("offline_only"):
                continue
            if pause and i > 1:
                time.sleep(pause)
            line, stdin = fill(step["run"], saved), step.get("stdin")
            if stdin is not None:
                stdin = fill(stdin if isinstance(stdin, str) else json.dumps(stdin), saved)
            code, out, err = home.run(line, stdin=stdin, env=step.get("env"))
            wrong = check(step.get("expect", {}), code, out, err, home)
            misses = home.take_misses()
            if misses and mode == "replay" and not step.get("expect", {}).get("offline_ok"):
                wrong.append("asked the internet for something not in the cassette (run with --record): "
                             + "; ".join(misses[:3]))
            if verbose or wrong:
                mark = f"{RED}FAIL{END}" if wrong else f"{GREEN}ok{END}  "
                print(f"  {mark} {i:>2}. {step['run']}")
                if verbose:
                    for line in (out + err).rstrip().splitlines()[:12]:
                        print(f"        {DIM}{line}{END}")
                for w in wrong:
                    print(f"        {RED}{w}{END}")
            if wrong:
                failures.append((i, step["run"], wrong))
            elif step.get("save"):
                try:
                    data = json.loads(out)
                    for name, path in step["save"].items():
                        saved[name] = str(dig(data, path))
                except (ValueError, KeyError, IndexError, TypeError):
                    failures.append((i, step["run"], ["could not save values from the answer"]))
    finally:
        home.remove()
    return len(steps), failures


def cmd_test(args):
    names = scenario_names(args.plugins)
    total_fail = 0
    for name in names:
        n, failures = run_scenario(name, "record" if args.record else ("live" if args.live else "replay"),
                                   args.verbose, args.pause if (args.record or args.live) else 0)
        status = f"{RED}FAIL{END}" if failures else f"{GREEN}ok{END}  "
        print(f"{status} {name}: {n - len(failures)} of {n} steps")
        total_fail += bool(failures)
    print(f"{len(names) - total_fail} of {len(names)} plugins pass their scenario.")
    return 1 if total_fail else 0


# --- smoke: nothing may crash -----------------------------------------------------------------------

def cmd_smoke(args):
    names = args.plugins or sorted(d for d in os.listdir(PLUGINS) if os.path.isfile(os.path.join(PLUGINS, d, "plugin.json")))
    bad = 0
    for name in names:
        home = Home(name, mode="replay", vault="")
        problems = []
        try:
            for cmd in (home.manifest.get("commands") or {}):
                for line in (f"{cmd} --help", cmd, f"{cmd} settings"):
                    if line.endswith(" settings") and not os.path.exists(os.path.join(home.folder, "settings.json")):
                        continue
                    code, out, err = home.run(line, timeout=60)
                    if "Traceback (most recent call last)" in out + err:
                        problems.append(f"`{line}` crashed: " + (err or out).strip().splitlines()[-1])
                    elif code == 124:
                        problems.append(f"`{line}` did not finish within 60s")
                    if line.endswith(" settings") and code == 0:
                        try:
                            json.loads(out)
                        except ValueError:
                            problems.append(f"`{line}` does not print JSON, as the settings form needs")
        finally:
            home.remove()
        if problems:
            bad += 1
            print(f"{RED}FAIL{END} {name}")
            for p in problems:
                print(f"     {p}")
        else:
            print(f"{GREEN}ok{END}   {name}")
    print(f"{len(names) - bad} of {len(names)} plugins run without crashing (offline, empty vault).")
    return 1 if bad else 0


# --- one command in a lasting home ------------------------------------------------------------------

def cmd_run(args):
    line = args.line
    if not line:
        sys.exit("python3 testenv/sim.py run <plugin> -- <command line>")
    sc = load_scenario(args.plugin) if os.path.exists(os.path.join(SCENARIOS, f"{args.plugin}.json")) else {}
    root = os.path.join(LASTING, args.plugin)
    os.makedirs(root, exist_ok=True)
    home = Home(args.plugin, root=root, mode="live" if args.live else "replay",
                now=None if args.live else sc.get("now", DEFAULT_NOW),
                vault=os.environ.get("SIM_VAULT") or vault_items(sc))
    code, out, err = home.run(line)
    sys.stdout.write(out)
    sys.stderr.write(err)
    for m in home.take_misses():
        print(f"{DIM}(not in the cassette: {m}; use --live to ask the internet){END}", file=sys.stderr)
    return code


# --- screens ----------------------------------------------------------------------------------------

def ensure_node():
    if not os.path.isdir(os.path.join(HERE, "node_modules", "esbuild")):
        print("Installing the screen tools once (esbuild, preact, playwright-core)...")
        subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--silent"], cwd=HERE, check=True)


def cmd_screen(args):
    ensure_node()
    names = args.plugins or sorted(
        d for d in os.listdir(PLUGINS) if os.path.isfile(os.path.join(PLUGINS, d, "plugin.json"))
        and {"window", "screen"} & set(json.load(open(os.path.join(PLUGINS, d, "plugin.json"), encoding="utf-8"))))
    bad = 0
    for name in names:
        sc = load_scenario(name) if os.path.exists(os.path.join(SCENARIOS, f"{name}.json")) else {"plugin": name}
        plugin = sc.get("plugin", name)
        mode = "record" if getattr(args, "record", False) else ("live" if args.live else "replay")
        home = Home(plugin, mode=mode, now=sc.get("now", DEFAULT_NOW), vault=vault_items(sc), stub=sc.get("stub"),
                programs=sc.get("programs"))
        try:
            for step in (sc.get("screen") or {}).get("before", []):
                home.run(step)
            spec = dict(sc.get("screen") or {}, plugin=plugin, home=home.root, out=os.path.join(OUT, plugin),
                        env=home.env(), images=bool(args.images), keep=bool(args.keep))
            spec_file = os.path.join(home.root, ".sim-screen.json")
            json.dump(spec, open(spec_file, "w"))
            p = subprocess.run(["node", os.path.join(RUNTIME, "screen.js"), spec_file], cwd=HERE)
            bad += p.returncode != 0
        finally:
            home.remove()
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test")
    t.add_argument("plugins", nargs="*")
    t.add_argument("--record", action="store_true", help="ask the internet and keep the answers")
    t.add_argument("--live", action="store_true", help="ask the internet, keep nothing")
    t.add_argument("-v", "--verbose", action="store_true")
    t.add_argument("--pause", type=float, default=0, help="seconds between steps when using the internet")
    s = sub.add_parser("smoke")
    s.add_argument("plugins", nargs="*")
    r = sub.add_parser("run")
    r.add_argument("plugin")
    r.add_argument("--live", action="store_true")
    r.add_argument("line", nargs=argparse.REMAINDER)
    sc = sub.add_parser("screen")
    sc.add_argument("plugins", nargs="*")
    sc.add_argument("--live", action="store_true")
    sc.add_argument("--record", action="store_true", help="ask the internet and add the answers to the cassette")
    sc.add_argument("--images", action="store_true", help="fetch product images with curl (needs internet)")
    sc.add_argument("--keep", action="store_true", help="leave the server running to look yourself")
    sv = sub.add_parser("serve")
    sv.add_argument("plugin")
    sv.add_argument("--live", action="store_true")
    sv.add_argument("--images", action="store_true")
    a = ap.parse_args()
    if a.cmd == "run":
        # Everything after the plugin lands here, flags too: read the flags before "--", run what follows it.
        if "--" in a.line:
            cut = a.line.index("--")
            flags, a.line = a.line[:cut], a.line[cut + 1:]
        else:
            flags = [x for x in a.line if x == "--live"]
            a.line = [x for x in a.line if x != "--live"]
        a.live = a.live or "--live" in flags
        sys.exit(cmd_run(a))
    if a.cmd == "serve":
        a.plugins, a.keep = [a.plugin], True
        sys.exit(cmd_screen(a))
    sys.exit({"test": cmd_test, "smoke": cmd_smoke, "screen": cmd_screen}[a.cmd](a))


if __name__ == "__main__":
    main()
