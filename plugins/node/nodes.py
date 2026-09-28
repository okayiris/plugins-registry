#!/usr/bin/env python3
"""Nodes for Iris: run commands on your own computer or server, without asking each time.

  nodes                         what nodes are paired and what keys are waiting
  nodes pair [label]            make a pairing key for a new device (shows what to run there)
  nodes run "<name>" "<command>" [--timeout N] [--cwd DIR]
  nodes revoke "<name>"         break the pairing; the device stops within a second
  nodes key rm "<label>"        throw away a pairing key that was never used
  nodes status "<name>"         one node in detail

The device side is node-agent.py (served at /node/agent by the bridge); `nodes pair` prints how to get it
and pair it. The bridge must answer the /node routes (see bridge-node.ts in this folder).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BRIDGE = (os.environ.get("IRIS_NODE_BRIDGE") or os.environ.get("IRIS_BRIDGE_URL")
          or "http://host.docker.internal:8790").rstrip("/")


def house_key():
    for name in ("NOVA_SLEUTEL", "NODE_HOUSE_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    for path in ("~/.telefoon-sleutel", "~/.nova-sleutel"):
        try:
            with open(os.path.expanduser(path)) as fh:
                key = fh.read().strip()
            if key:
                return key
        except OSError:
            pass
    return ""


def api(path, method="GET", body=None, timeout=30, auth=True):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BRIDGE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "iris-node-plugin/1.0")
    if auth:
        key = house_key()
        if not key:
            sys.exit("nodes: no house key found (~/.telefoon-sleutel or NOVA_SLEUTEL)")
        req.add_header("X-Nova-Sleutel", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except ValueError:
            d = {}
        msg = d.get("fout") or d.get("error") or "HTTP %d" % e.code
        if e.code == 401:
            sys.exit("nodes: the bridge did not accept the house key (%s)" % msg)
        sys.exit("nodes: %s" % msg)
    except urllib.error.URLError as e:
        sys.exit("nodes: the bridge is not reachable at %s (%s)" % (BRIDGE, e.reason))


def age(ms):
    if not ms:
        return "?"
    secs = max(0, int((time.time() * 1000 - ms) / 1000))
    if secs < 60:
        return "%ds ago" % secs
    if secs < 3600:
        return "%dm ago" % (secs // 60)
    return "%dh ago" % (secs // 3600)


def cmd_list(args):
    d = api("/node")
    nodes = d.get("nodes") or []
    keys = d.get("keys") or []
    if not nodes and not keys:
        print("no nodes yet. `nodes pair` makes a key for a new device.")
        return 0
    for n in nodes:
        print("%s  %s  %s  (%s)" % (
            n["name"], "online" if n.get("online") else "offline",
            "%s, %s" % (n.get("os") or "?", n.get("host") or "?"), "seen %s" % age(n.get("lastSeen"))))
        if n.get("allow"):
            print("    allow: %s" % ", ".join(n["allow"]))
    for k in keys:
        print("key %r is waiting (made %s, expires %s)" % (k["label"], age(k["created"]), age(k["expires"])))
    return 0


def cmd_pair(args):
    label = args.get("label") or (args.get("_")[0] if args.get("_") else None)
    body = {"label": label} if label else {}
    d = api("/node/key", method="POST", body=body)
    key = d["key"]
    label = d["label"]
    info = api("/node")
    public = (info.get("publicUrl") or "").rstrip("/") or BRIDGE
    agent = (info.get("agent") or "/node/agent")
    print("Pairing key for %r (works once, valid 10 minutes)." % label)
    print(key)
    print()
    print("On the device:")
    print("  curl -fsSL %s%s -o /tmp/iris-node-agent.py" % (public, agent))
    print("  python3 /tmp/iris-node-agent.py pair --bridge %s --key %s" % (public, key))
    print("  python3 /tmp/iris-node-agent.py install")
    print()
    print("`install` keeps it running from now on (launchd on macOS, systemd on Linux).")
    return 0


def cmd_run(args):
    pos = args.get("_") or []
    if len(pos) < 2:
        sys.exit("usage: nodes run \"<name>\" \"<command>\" [--timeout N] [--cwd DIR]")
    name, cmd = pos[0], pos[1]
    body = {"name": name, "cmd": cmd}
    if args.get("timeout"):
        body["timeout"] = int(args["timeout"])
    if args.get("cwd"):
        body["cwd"] = args["cwd"]
    d = api("/node/run", method="POST", body=body, timeout=min(600, int(body.get("timeout") or 60)) + 30)
    if d.get("stdout"):
        sys.stdout.write(d["stdout"] if d["stdout"].endswith("\n") else d["stdout"] + "\n")
    if d.get("stderr"):
        sys.stderr.write(d["stderr"] if d["stderr"].endswith("\n") else d["stderr"] + "\n")
    if d.get("timedOut"):
        print("[timed out after %ss]" % (body.get("timeout") or 60))
    if d.get("truncated"):
        print("[output was cut off]")
    if d.get("exit"):
        print("[exit %s]" % d["exit"])
    return int(d.get("exit") or 0)


def cmd_revoke(args):
    pos = args.get("_") or []
    if not pos:
        sys.exit("usage: nodes revoke \"<name>\"")
    d = api("/node/revoke", method="POST", body={"name": pos[0]})
    print("revoked %r; it stops within a second and its secret no longer works." % d.get("name"))
    return 0


def cmd_key_rm(args):
    pos = args.get("_") or []
    if not pos:
        sys.exit("usage: nodes key rm \"<label>\"")
    d = api("/node/key/rm", method="POST", body={"label": pos[0]})
    print("removed %s waiting key(s)" % d.get("removed", 0))
    return 0


def cmd_status(args):
    pos = args.get("_") or []
    if not pos:
        sys.exit("usage: nodes status \"<name>\"")
    d = api("/node")
    ref = pos[0].lower()
    n = next((x for x in (d.get("nodes") or [])
              if x["id"] == ref or x["name"].lower() == ref or x["name"].lower().startswith(ref)), None)
    if not n:
        sys.exit("nodes: no node %r" % pos[0])
    print("%s (id %s)" % (n["name"], n["id"]))
    print("  %s, %s" % (n.get("os") or "?", n.get("host") or "?"))
    print("  %s, last seen %s" % ("online" if n.get("online") else "offline", age(n.get("lastSeen"))))
    print("  paired %s" % age(n.get("created")))
    if n.get("allow"):
        print("  allow: %s" % ", ".join(n["allow"]))
    return 0


def parse(argv):
    args = {"_": []}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            args[key] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            args["_"].append(a)
            i += 1
    return args


def main():
    args = parse(sys.argv[1:])
    pos = args["_"]
    what = pos[0] if pos else "list"
    rest = args.copy()
    rest["_"] = pos[1:]
    if what in ("ls", "list"):
        return cmd_list(rest)
    if what == "pair":
        return cmd_pair(rest)
    if what == "run":
        return cmd_run(rest)
    if what == "revoke":
        return cmd_revoke(rest)
    if what == "key" and rest["_"] and rest["_"][0] == "rm":
        rest["_"] = rest["_"][1:]
        return cmd_key_rm(rest)
    if what == "status":
        return cmd_status(rest)
    sys.exit(__doc__)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)
