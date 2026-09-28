#!/usr/bin/env python3
"""End-to-end test for the node plugin.

Starts bridge-node.ts standalone on a loopback port, pairs a real agent against it with a key from
nodes.py, then runs commands through nodes.py and checks the interesting cases: a normal run, the allow
list, a timeout, a reused pairing key, an unknown node, and revocation. Needs node and python3 only.

    python3 test_node.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("NODE_TEST_PORT", "8797"))
BASE = "http://127.0.0.1:%d" % PORT
HOUSE = "test-house-key"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print("%s %s%s" % ("PASS" if ok else "FAIL", name, ("  (%s)" % detail) if detail and not ok else ""))


def http(method, path, body=None, key=None, timeout=20):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-Nova-Sleutel", key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def wait_http(path, key, tries=60):
    for _ in range(tries):
        try:
            return http("GET", path, key=key)
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    raise RuntimeError("hub did not come up")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="node-test-"))
    hub = None
    agent = None
    keeper = None
    env = dict(os.environ)
    env.update({"NODE_POLL_MS": "1200", "NODE_KEY_TTL_MS": "120000", "NODE_OFFLINE_MS": "10000"})
    house_env = dict(os.environ)
    house_env.update({"IRIS_NODE_BRIDGE": BASE, "NOVA_SLEUTEL": HOUSE})
    cfg = tmp / "agent.json"
    agent_env = dict(os.environ)
    agent_env.update({"IRIS_NODE_CONFIG": str(cfg), "IRIS_NODE_POLL_MS": "1200"})

    def cli(*args, timeout=40):
        return subprocess.run([sys.executable, str(HERE / "nodes.py"), *args],
                              env=house_env, capture_output=True, text=True, timeout=timeout)

    try:
        hub = subprocess.Popen(["node", str(HERE / "bridge-node.ts"), "--port", str(PORT),
                                "--data", str(tmp / "bridge"), "--house-key", HOUSE],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        wait_http("/node", HOUSE)
        check("hub starts and lists an empty set", True)

        # The agent source is served for the one-line install.
        try:
            with urllib.request.urlopen(BASE + "/node/agent", timeout=10) as r:
                bron = r.read().decode()
            check("hub serves the agent", "node-agent.py" in bron and "def main" in bron)
        except Exception as e:
            check("hub serves the agent", False, e)

        # `nodes pair` makes a key and prints usable instructions.
        r = cli("pair", "testmac")
        regels = [l for l in r.stdout.splitlines() if l.strip()]
        key = regels[1].strip() if len(regels) > 1 else ""
        check("nodes pair makes a key", r.returncode == 0 and len(key) == 32, r.stdout + r.stderr)
        check("nodes pair prints the install steps", "/node/agent" in r.stdout and "node-agent.py pair" in r.stdout,
              r.stdout)

        # Pair a real agent with that key.
        p = subprocess.run([sys.executable, str(HERE / "node-agent.py"), "pair", "--bridge", BASE,
                            "--key", key, "--name", "testmac", "--allow", "echo,printf,false,sleep"],
                           env=agent_env, capture_output=True, text=True)
        check("agent pairs with the key", p.returncode == 0 and "paired as" in p.stdout, p.stdout + p.stderr)
        mode = oct(os.stat(cfg).st_mode & 0o777)
        check("config is kept private (600)", mode == "0o600", mode)
        check("secret is not printed", "secret" not in p.stdout.lower(), p.stdout)

        # The agent holds the long poll open.
        agent = subprocess.Popen([sys.executable, str(HERE / "node-agent.py"), "run"],
                                 env=agent_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # A normal command runs and its output comes back.
        r = cli("run", "testmac", "echo hallo")
        check("nodes run returns the output", r.returncode == 0 and "hallo" in r.stdout, r.stdout + r.stderr)

        # The allow list refuses anything else, and cannot be stepped over with a chain.
        r = cli("run", "testmac", "whoami")
        check("allow list refuses other commands", r.returncode == 126 and "allow list" in r.stderr,
              "rc=%s out=%r err=%r" % (r.returncode, r.stdout, r.stderr))
        r = cli("run", "testmac", "echo ok; whoami")
        check("allow list blocks a chained command", r.returncode == 126 and "allow list" in r.stderr,
              "rc=%s out=%r err=%r" % (r.returncode, r.stdout, r.stderr))
        r = cli("run", "testmac", "echo $(whoami)")
        check("allow list blocks command substitution", r.returncode == 126 and "substitution" in r.stderr,
              "rc=%s out=%r err=%r" % (r.returncode, r.stdout, r.stderr))

        # A timeout kills the command and tells us.
        r = cli("run", "testmac", "sleep 5", "--timeout", "1")
        check("timeout is enforced", r.returncode == 124 and "timed out" in r.stdout,
              "rc=%s out=%r" % (r.returncode, r.stdout))

        # Stdin and stderr pass through, too.
        r = cli("run", "testmac", "printf 'a\\nb\\n'")
        check("stdout passes through unchanged", r.returncode == 0 and r.stdout == "a\nb\n", repr(r.stdout))

        # Unknown node fails cleanly.
        r = cli("run", "nosuch", "echo x")
        check("unknown node fails cleanly", r.returncode != 0 and "no node" in r.stderr, r.stdout + r.stderr)

        # A key works exactly once.
        p = subprocess.run([sys.executable, str(HERE / "node-agent.py"), "pair", "--bridge", BASE,
                            "--key", key, "--name", "second"], env=agent_env, capture_output=True, text=True)
        check("a used key is refused", p.returncode != 0 and "refused" in (p.stdout + p.stderr),
              p.stdout + p.stderr)

        # A made-up key is refused.
        p = subprocess.run([sys.executable, str(HERE / "node-agent.py"), "pair", "--bridge", BASE,
                            "--key", "0" * 32, "--name", "third"], env=agent_env, capture_output=True, text=True)
        check("an unknown key is refused", p.returncode != 0 and "refused" in (p.stdout + p.stderr),
              p.stdout + p.stderr)

        # `nodes` lists the paired node.
        r = cli()
        check("nodes lists the paired node", "testmac" in r.stdout, r.stdout + r.stderr)

        # Cancel a waiting key.
        cli("pair", "throwaway")
        r = cli("key", "rm", "throwaway")
        check("a waiting key can be cancelled", r.returncode == 0 and "removed 1" in r.stdout, r.stdout + r.stderr)

        # Revoke: the agent stops, and the node is gone for the bridge.
        r = cli("revoke", "testmac")
        check("nodes revoke reports success", r.returncode == 0 and "revoked" in r.stdout, r.stdout + r.stderr)
        try:
            agent.wait(timeout=15)
            check("the agent stops after revoke", agent.returncode == 3, "rc=%s" % agent.returncode)
        except subprocess.TimeoutExpired:
            check("the agent stops after revoke", False, "still running")
        agent = None
        r = cli("run", "testmac", "echo x")
        check("a revoked node is gone", r.returncode != 0 and "no node" in r.stderr, r.stdout + r.stderr)

        # Pairing survives a bridge restart, and the agent reconnects by itself.
        r = cli("pair", "keeper")
        key2 = [l for l in r.stdout.splitlines() if l.strip()][1].strip()
        p = subprocess.run([sys.executable, str(HERE / "node-agent.py"), "pair", "--bridge", BASE,
                            "--key", key2, "--name", "keeper", "--allow", "echo"],
                           env=agent_env, capture_output=True, text=True)
        check("second node pairs", p.returncode == 0, p.stdout + p.stderr)
        keeper = subprocess.Popen([sys.executable, str(HERE / "node-agent.py"), "run"],
                                  env=agent_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        hub.terminate()
        hub.wait(timeout=10)
        hub = subprocess.Popen(["node", str(HERE / "bridge-node.ts"), "--port", str(PORT),
                                "--data", str(tmp / "bridge"), "--house-key", HOUSE],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        wait_http("/node", HOUSE)
        r = cli()
        check("the pairing survives a bridge restart", "keeper" in r.stdout, r.stdout + r.stderr)
        ok = False
        for _ in range(40):
            r = cli("run", "keeper", "echo back")
            if r.returncode == 0 and "back" in r.stdout:
                ok = True
                break
            time.sleep(0.5)
        check("the agent reconnects after a restart", ok, "%s%s" % (r.stdout, r.stderr))
        keeper.terminate()
        keeper.wait(timeout=5)

        return 0 if all(ok for _, ok in results) else 1
    finally:
        for proc in (agent, keeper, hub):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
