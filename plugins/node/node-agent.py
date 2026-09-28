#!/usr/bin/env python3
"""Node agent: the small program that turns a computer into a node for Iris.

Install it on a Mac, a server or a Raspberry Pi, pair it once with a key from the house, and from then
on Iris runs commands there through the bridge. No prompt per command: the pairing is the approval.
Revoke the node in the house (`node revoke "<name>"`) or here (`node-agent.py revoke`), and it stops
within a second.

  node-agent.py pair --bridge https://... --key <key> [--name "Mac Studio"] [--allow "git,ls,cat"] [--cwd DIR]
      pair once; the key comes from `node pair` in the chat and works once, for ten minutes
  node-agent.py run
      the permanent connection: long-poll the bridge, run what it sends, send the output back
  node-agent.py status
      what this node is paired to, and whether the bridge still knows it
  node-agent.py revoke
      unpair from this side and throw the key away
  node-agent.py install [--config PATH]
      keep `run` going as a service: launchd on macOS, systemd on Linux
  node-agent.py uninstall
      stop the service (the pairing stays in the config; use revoke to drop it too)
  node-agent.py once
      handle at most one command and exit (for tests and debugging)

The config lives in ~/.iris-node/config.json (mode 600) and holds the paired secret. It is never printed.

  --allow "git,ls"     only commands that start with one of these words run; empty means all
  --deny "rm -rf"      a command that starts with this is refused, whatever --allow says
  --cwd DIR            run there by default
  --timeout N          default seconds per command (the bridge can lower, never raise past N)
"""
import json
import os
import platform
import re
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.environ.get("IRIS_NODE_CONFIG") or os.path.expanduser("~/.iris-node/config.json")
POLL_MS = int(os.environ.get("IRIS_NODE_POLL_MS", "25000"))
MAX_OUT = 256 * 1024
MAX_TIMEOUT = 600
LOOP = True


def out(*a):
    print(*a, flush=True)


def load_config(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_config(path, cfg):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)


def http(url, method="GET", body=None, secret=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if secret:
        req.add_header("Authorization", "Bearer " + secret)
    req.add_header("User-Agent", "iris-node/1.0")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            return {"raw": raw.decode("utf-8", "replace")}


class Revoked(Exception):
    pass


def api(cfg, path, method="GET", body=None, timeout=30):
    base = cfg["bridge"].rstrip("/")
    try:
        return http(base + path, method=method, body=body, secret=cfg.get("secret"), timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise Revoked(e.code)
        try:
            d = json.load(e)
        except ValueError:
            d = {}
        raise RuntimeError(d.get("fout") or d.get("error") or "HTTP %d" % e.code)
    except urllib.error.URLError as e:
        raise OSError("the bridge cannot be reached (%s)" % e.reason)


def bridge_is_https(cfg):
    return cfg["bridge"].startswith("https://")


def default_shell():
    if platform.system() == "Darwin":
        return "/bin/zsh"
    for s in ("/bin/bash", "/bin/sh"):
        if os.path.exists(s):
            return s
    return "/bin/sh"


def allowed(cfg, cmd):
    """An allow list is a fence, so it must not be stepped over with `;` or a pipe: every simple command
    in a chain has to match. `--allow git` permits `git status` and `git push`, not `git; curl evil`
    or `echo $(git)`.

    Empty allow means everything (minus deny) runs; that is the normal case, where the owner trusts the
    house and the pairing is the approval. Set allow for a machine that may only serve a few tools.
    """
    allow = cfg.get("allow") or []
    deny = cfg.get("deny") or []
    segments = [s.strip() for s in re.split(r"\|\||&&|[;|&\n]", cmd) if s.strip()]
    for bad in deny:
        if any(s.startswith(bad) for s in (segments or [cmd])):
            return False, "refused by the node's deny list"
    if not allow:
        return True, ""
    if "`" in cmd or "$(" in cmd:
        return False, "command substitution is not allowed on this node"
    for s in segments:
        words = s.split()
        while words and "=" in words[0] and "/" not in words[0].split("=", 1)[0]:
            words = words[1:]  # skip leading VAR=value assignments
        s = " ".join(words)
        if not s or not any(s == a or s.startswith(a + " ") for a in allow):
            return False, "not in the node's allow list"
    return True, ""


def run_command(cfg, job):
    cmd = str(job.get("cmd") or "")
    if not cmd.strip():
        return {"exit": 2, "stdout": "", "stderr": "empty command", "truncated": False, "timedOut": False, "ms": 0}
    if os.geteuid() == 0 and not cfg.get("allow_root"):
        return {"exit": 2, "stdout": "", "stderr": "refusing to run as root", "truncated": False, "timedOut": False, "ms": 0}
    ok, why = allowed(cfg, cmd)
    if not ok:
        return {"exit": 126, "stdout": "", "stderr": why, "truncated": False, "timedOut": False, "ms": 0}
    cap = min(MAX_TIMEOUT, int(cfg.get("timeout") or 60))
    secs = int(job.get("timeout") or cap)
    if secs > MAX_TIMEOUT * 2:  # a bridge that speaks milliseconds
        secs = round(secs / 1000)
    secs = min(cap, max(1, secs))
    cwd = job.get("cwd") or cfg.get("cwd") or None
    shell = cfg.get("shell") or default_shell()
    login = bool(cfg.get("login_shell", True))
    argv = [shell, "-lc", cmd] if login else [shell, "-c", cmd]
    start = time.time()
    timed_out = False
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
        )
    except OSError as e:
        return {"exit": 127, "stdout": "", "stderr": str(e), "truncated": False, "timedOut": False, "ms": 0}
    try:
        raw_out, raw_err = proc.communicate(timeout=secs)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except OSError:
            proc.kill()
        raw_out, raw_err = proc.communicate()
    trunc = len(raw_out) > MAX_OUT or len(raw_err) > MAX_OUT
    return {
        "exit": 124 if timed_out else (proc.returncode or 0),
        "stdout": raw_out[:MAX_OUT].decode("utf-8", "replace"),
        "stderr": raw_err[:MAX_OUT].decode("utf-8", "replace"),
        "truncated": trunc,
        "timedOut": timed_out,
        "ms": int((time.time() - start) * 1000),
    }


def pair(args):
    cfg_path = args.get("config") or DEFAULT_CONFIG
    bridge = (args.get("bridge") or os.environ.get("IRIS_BRIDGE_URL") or "").rstrip("/")
    key = args.get("key")
    if not bridge or not key:
        sys.exit("pair needs --bridge <url> and --key <key>; ask for a key with `node pair` in the chat")
    if bridge.startswith("http://") and "localhost" not in bridge and "127.0.0.1" not in bridge:
        out("warning: this bridge is plain http; the secret and every command travel unencrypted")
    body = {
        "key": key,
        "name": args.get("name") or socket.gethostname(),
        "os": "%s %s" % (platform.system(), platform.release()),
        "host": socket.gethostname(),
        "allow": [a for a in (args.get("allow") or "").split(",") if a.strip()],
    }
    try:
        d = http(bridge + "/node/pair", method="POST", body=body, timeout=30)
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except ValueError:
            d = {}
        sys.exit("pairing refused: %s" % (d.get("fout") or "HTTP %d" % e.code))
    except OSError as e:
        sys.exit("the bridge cannot be reached (%s)" % e)
    if not d.get("secret"):
        sys.exit("pairing refused: the bridge gave no secret")
    cfg = {
        "bridge": bridge,
        "id": d["node"]["id"],
        "name": d["node"]["name"],
        "secret": d["secret"],
        "allow": body["allow"],
        "deny": [a for a in (args.get("deny") or "").split(",") if a.strip()],
        "cwd": args.get("cwd") or "",
        "timeout": int(args.get("timeout") or 60),
        "shell": args.get("shell") or "",
        "login_shell": True,
    }
    save_config(cfg_path, cfg)
    out("paired as %r (id %s)" % (cfg["name"], cfg["id"]))
    out("start it with: %s %s run" % (sys.executable, os.path.abspath(__file__)))
    out("keep it running always: %s %s install" % (sys.executable, os.path.abspath(__file__)))


def next_job(cfg, wait=True):
    timeout = (POLL_MS / 1000.0) + 15 if wait else 20
    d = api(cfg, "/node/next", timeout=timeout)
    job = d.get("job") if isinstance(d, dict) else None
    return job or None


def loop(args):
    cfg_path = args.get("config") or DEFAULT_CONFIG
    cfg = load_config(cfg_path)
    if not cfg.get("bridge") or not cfg.get("secret"):
        sys.exit("not paired yet; run `pair` first (or set IRIS_NODE_CONFIG to the right file)")
    out("node %r connected to %s" % (cfg.get("name"), cfg["bridge"]))
    once_only = bool(args.get("once")) or os.environ.get("IRIS_NODE_ONCE") == "1"
    backoff = 1
    while True:
        try:
            job = next_job(cfg)
            backoff = 1
        except Revoked:
            out("this node was revoked; stopping. Pair again with a new key to come back.")
            return 3
        except (OSError, RuntimeError) as e:
            out("bridge not reachable: %s (trying again in %ss)" % (e, backoff))
            time.sleep(backoff)
            backoff = min(30, backoff * 2)
            continue
        if not job:
            if once_only:
                return 0
            continue
        result = run_command(cfg, job)
        try:
            api(cfg, "/node/result", method="POST", body=dict(id=job["id"], **result), timeout=30)
        except Revoked:
            out("this node was revoked; stopping.")
            return 3
        except (OSError, RuntimeError) as e:
            out("could not send the answer back: %s" % e)
        if result.get("stdout"):
            sys.stdout.write(result["stdout"] if result["stdout"].endswith("\n") else result["stdout"] + "\n")
        if result.get("stderr"):
            sys.stderr.write(result["stderr"] if result["stderr"].endswith("\n") else result["stderr"] + "\n")
        out("[%s exited %s in %sms%s]" % (job["id"], result["exit"], result["ms"],
                                          ", timed out" if result["timedOut"] else ""))
        if once_only:
            return 0


def status(args):
    cfg_path = args.get("config") or DEFAULT_CONFIG
    cfg = load_config(cfg_path)
    if not cfg.get("bridge"):
        out("not paired (no config at %s)" % cfg_path)
        return 0
    out("node %r (id %s)" % (cfg.get("name"), cfg.get("id")))
    out("bridge %s" % cfg["bridge"])
    if cfg.get("allow"):
        out("allow: %s" % ", ".join(cfg["allow"]))
    if cfg.get("deny"):
        out("deny: %s" % ", ".join(cfg["deny"]))
    try:
        d = api(cfg, "/node/me", timeout=15)
        out("the bridge knows this node: online=%s last seen %s" % (d.get("online"), d.get("lastSeen")))
    except Revoked:
        out("the bridge does not know this node any more: it was revoked")
        return 3
    except (OSError, RuntimeError) as e:
        out("cannot ask the bridge: %s" % e)
        return 1
    return 0


def revoke(args):
    cfg_path = args.get("config") or DEFAULT_CONFIG
    cfg = load_config(cfg_path)
    if cfg.get("bridge") and cfg.get("secret"):
        try:
            api(cfg, "/node/bye", method="POST", body={}, timeout=15)
            out("unpaired at the bridge")
        except (OSError, RuntimeError, Revoked):
            out("could not tell the bridge; dropping the local key anyway")
    try:
        os.remove(cfg_path)
    except OSError:
        pass
    out("this device is no longer a node")
    return 0


def service_paths():
    if platform.system() == "Darwin":
        return os.path.expanduser("~/Library/LaunchAgents/com.iris.node.plist"), None
    return None, os.path.expanduser("~/.config/systemd/user/iris-node.service")


def install(args):
    cfg_path = args.get("config") or DEFAULT_CONFIG
    agent = os.path.abspath(__file__)
    py = sys.executable
    system = platform.system()
    if system == "Darwin":
        plist, _ = service_paths()
        os.makedirs(os.path.dirname(plist), exist_ok=True)
        log = os.path.expanduser("~/.iris-node/node.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        body = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.iris.node</string>
  <key>ProgramArguments</key><array>
    <string>%s</string><string>%s</string><string>run</string><string>--config</string><string>%s</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>%s</string>
  <key>StandardErrorPath</key><string>%s</string>
</dict></plist>
""" % (py, agent, cfg_path, log, log)
        with open(plist, "w") as fh:
            fh.write(body)
        subprocess.run(["launchctl", "unload", plist], capture_output=True)
        r = subprocess.run(["launchctl", "load", "-w", plist], capture_output=True, text=True)
        if r.returncode:
            sys.exit("launchctl could not load the service: %s" % (r.stderr.strip() or r.returncode))
        out("installed. It starts now and again at every login. Check with: launchctl list | grep iris.node")
        return 0
    if system == "Linux":
        _, unit = service_paths()
        os.makedirs(os.path.dirname(unit), exist_ok=True)
        with open(unit, "w") as fh:
            fh.write("[Unit]\nDescription=Iris node agent\nAfter=network-online.target\n\n"
                     "[Service]\nExecStart=%s %s run --config %s\nRestart=always\nRestartSec=5\n\n"
                     "[Install]\nWantedBy=default.target\n" % (py, agent, cfg_path))
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        r = subprocess.run(["systemctl", "--user", "enable", "--now", "iris-node.service"], capture_output=True, text=True)
        if r.returncode:
            sys.exit("systemd could not start the service: %s" % (r.stderr.strip() or r.returncode))
        out("installed and started. Check with: systemctl --user status iris-node")
        return 0
    sys.exit("automatic install is only for macOS and Linux; run `run` under your own supervisor on %s" % system)


def uninstall(args):
    system = platform.system()
    if system == "Darwin":
        plist, _ = service_paths()
        subprocess.run(["launchctl", "unload", plist], capture_output=True)
        try:
            os.remove(plist)
        except OSError:
            pass
        out("service removed")
        return 0
    if system == "Linux":
        _, unit = service_paths()
        subprocess.run(["systemctl", "--user", "disable", "--now", "iris-node.service"], capture_output=True)
        try:
            os.remove(unit)
        except OSError:
            pass
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        out("service removed")
        return 0
    sys.exit("nothing to uninstall on %s" % system)


def parse(argv):
    args = {}
    positional = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            if key in ("once",):
                args[key] = True
                i += 1
                continue
            val = argv[i + 1] if i + 1 < len(argv) else ""
            args[key] = val
            i += 2
        else:
            positional.append(a)
            i += 1
    return positional, args


def main():
    positional, args = parse(sys.argv[1:])
    wat = positional[0] if positional else "help"
    if wat == "pair":
        return pair(args)
    if wat == "run":
        return loop(args)
    if wat == "once":
        args["once"] = True
        return loop(args)
    if wat == "status":
        return status(args)
    if wat == "revoke":
        return revoke(args)
    if wat == "install":
        return install(args)
    if wat == "uninstall":
        return uninstall(args)
    sys.exit(__doc__)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)
