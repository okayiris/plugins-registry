#!/usr/bin/env python3
"""process-monitor - Process Monitor: what runs inside this house.

Reads /proc and shows every process with its pid, name, user, cpu, memory and how
long it has been running. Stopping never happens on its own: `stop` first asks for
a confirmation, and only a second run with `--ja` sends the signal. The floor
(pid 1, the desktop, the assistant itself) and the house's own watchers are
protected and can never be stopped from here.

Also shows the workbench boxes (throwaway workshops) that are busy right now,
by looking for the running `werkplek` / `workbench` jobs in /proc.

Usage:
  processes [--json] [--all]        short answer, or everything as JSON
  processes procs [--all] [--json]  the process list
  processes boxes [--json]          the busy workbench boxes
  processes stop <pid> [--hard] [--ja]
  processes help

Read-only except `stop ... --ja`.
"""

import json
import os
import pwd
import signal
import sys
import time
import urllib.request
import urllib.error

HZ = os.sysconf("SC_CLK_TCK") or 100
PAGE = os.sysconf("SC_PAGE_SIZE") or 4096

# The floor of the house: these keep the desktop and the connection alive and are
# never stopped from here. The bridge on the other side does the same.
FLOOR_NAMES = {
    "websockify", "Xvfb", "x11vnc", "xfce4-session", "xfce4-panel", "xfdesktop",
    "xfconfd", "xfwm4", "xfsettingsd", "xfce4-notifyd", "xfce4-power-manager",
    "Thunar", "dbus-launch", "dbus-daemon", "panel-6-systray", "panel-8-pulseau",
    "panel-14-action", "at-spi-bus-launcher", "at-spi2-registryd",
}
# "own bridge": in this container that is the assistant's brain and the little
# watchers that keep plugins and screens up to date.
BRIDGE_PATTERNS = (
    "/usr/local/bin/dsh",
    'stat -c "%n %Y %s"',
)



def human_duration(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m{s:02d}s" if s else f"{m}m"
    if seconds < 86400:
        u, r = divmod(seconds, 3600)
        m = r // 60
        return f"{u}h{m:02d}m" if m else f"{u}h"
    d, r = divmod(seconds, 86400)
    u = r // 3600
    return f"{d}d{u:02d}h" if u else f"{d}d"


def boot_time():
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("btime "):
                    return int(line.split()[1])
    except OSError:
        pass
    return int(time.time())


def read_stat(pid):
    with open(f"/proc/{pid}/stat", "rb") as f:
        raw = f.read().decode("utf-8", "replace")
    rp = raw.rfind(")")
    name = raw[raw.find("(") + 1:rp]
    fields = raw[rp + 2:].split()
    return {
        "name": name,
        "status": fields[0],
        "ppid": int(fields[1]),
        "utime": int(fields[11]),
        "stime": int(fields[12]),
        "start": int(fields[19]),
    }


def read_status(pid):
    uid, rss = None, 0
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("Uid:"):
                    uid = line.split()[1]
                elif line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
    except OSError:
        pass
    return uid, rss


def read_cmd(pid, name):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read().decode("utf-8", "replace")
    except OSError:
        return f"[{name}]"
    cmd = " ".join(part for part in raw.split("\0") if part).strip()
    return cmd or f"[{name}]"


def username(uid):
    if uid is None:
        return "?"
    try:
        return pwd.getpwuid(int(uid)).pw_name
    except (KeyError, ValueError):
        return uid


def own_tree():
    """Our own pids and those of our parents: those we never stop."""
    tree = {os.getpid()}
    pid = os.getpid()
    for _ in range(64):
        try:
            parent = read_stat(pid)["ppid"]
        except OSError:
            break
        if parent <= 1 or parent in tree:
            tree.add(1)
            break
        tree.add(parent)
        pid = parent
    return tree


def protected_reason(pid, ppid, name, cmd, tree, status):
    if pid == 1:
        return "the floor of this house"
    if pid in tree:
        return "this command itself"
    if status == "Z":
        return "zombie"
    if name in FLOOR_NAMES:
        return "the floor (desktop)"
    if any(p in cmd for p in BRIDGE_PATTERNS):
        return "the house's own bridge"
    if cmd.startswith("[") and cmd.endswith("]"):
        return "system process"
    return None


def collect_procs():
    now = time.time()
    b = boot_time()
    tree = own_tree()
    rows = []
    for name_pid in os.listdir("/proc"):
        if not name_pid.isdigit():
            continue
        pid = int(name_pid)
        if pid == os.getpid():
            continue
        try:
            st = read_stat(pid)
        except (OSError, ValueError, IndexError):
            continue
        name = st["name"]
        if st["status"] == "Z":
            zombie = True
        else:
            zombie = False
        cmd = read_cmd(pid, name)
        uid, rss_kb = read_status(pid)
        if rss_kb:
            mb = round(rss_kb / 1024, 1)
        else:
            mb = 0.0
        start_ep = b + st["start"] / HZ
        age = max(0.0, now - start_ep)
        ticks = st["utime"] + st["stime"]
        cpu = round(100.0 * (ticks / HZ) / age, 1) if age > 0.5 else 0.0
        reason = protected_reason(pid, st["ppid"], name, cmd, tree, st["status"])
        rows.append({
            "pid": pid,
            "ppid": st["ppid"],
            "naam": name,
            "gebruiker": username(uid),
            "cpu": cpu,
            "mb": mb,
            "sinds": int(start_ep),
            "sinds_tekst": human_duration(age),
            "commando": cmd,
            "zombie": zombie,
            "beschermd": bool(reason),
            "reden": reason,
        })
    rows.sort(key=lambda r: (-r["cpu"], -r["mb"], r["pid"]))
    return rows


def collect_boxes():
    """Workbenches running right now: their wrapper process is in /proc, the box
    itself runs next to this house. As long as the wrapper lives, the box is busy."""
    boxes = []
    for name_pid in os.listdir("/proc"):
        if not name_pid.isdigit():
            continue
        pid = int(name_pid)
        if pid == os.getpid():
            continue
        try:
            st = read_stat(pid)
            cmd = read_cmd(pid, st["name"])
        except (OSError, ValueError, IndexError):
            continue
        parts = cmd.split()
        if not parts:
            continue
        # Only the real wrapper itself, not every shell that mentions the word:
        # node <script> <folder> <command...>, with script werkplek or workbench(.js).
        if os.path.basename(parts[0]).lower() not in ("node", "nodejs"):
            continue
        i = 1
        while i < len(parts) and os.path.basename(parts[i]).lower() in ("node", "nodejs"):
            i += 1
        if i >= len(parts):
            continue
        if os.path.basename(parts[i]).lower() not in ("werkplek", "workbench", "workbench.js"):
            continue
        folder = parts[i + 1] if len(parts) > i + 1 else "?"
        command = " ".join(parts[i + 2:]) if len(parts) > i + 2 else ""
        start_ep = boot_time() + st["start"] / HZ
        age = max(0.0, time.time() - start_ep)
        boxes.append({
            "pid": pid,
            "map": folder,
            "commando": command,
            "sinds": int(start_ep),
            "leeftijd": int(age),
            "leeftijd_tekst": human_duration(age),
            "status": "busy",
        })
    boxes.sort(key=lambda r: r["sinds"])
    return boxes


def service_state():
    url = os.environ.get("WERKPLEK_URL") or os.environ.get("WORKBENCH_URL") \
        or "http://host.docker.internal:8795"
    state = {"url": url, "bereikbaar": False, "melding": ""}
    try:
        with urllib.request.urlopen(url + "/", timeout=3) as answer:
            state["bereikbaar"] = True
            state["melding"] = answer.status
    except urllib.error.HTTPError as err:
        # A route that does not exist still means the service answers.
        state["bereikbaar"] = True
        state["melding"] = err.code
    except Exception as err:  # no workbench in this house
        state["melding"] = str(err)
    return state


def boxes_view():
    return {"dienst": service_state(), "boxen": collect_boxes()}


# ---------- output ----------

def procs_human(procs, everything):
    visible = [p for p in procs if everything or not p["zombie"]]
    if not visible:
        return "Nothing special is running in this house."
    lines = [f"{'PID':>7}  {'USER':<9} {'CPU':>5} {'MB':>7}  {'AGE':<8} NAME"]
    for p in visible:
        flag = "*" if p["beschermd"] else " "
        command = p["commando"]
        if len(command) > 62:
            command = command[:59] + "..."
        lines.append(
            f"{p['pid']:>7}{flag} {p['gebruiker']:<9} {p['cpu']:>4}% {p['mb']:>7}  "
            f"{p['sinds_tekst']:<8} {p['naam']}  {command}"
        )
    lines.append("")
    lines.append("* = protected, never stopped")
    return "\n".join(lines)


def summary(procs, boxes, service):
    alive = [p for p in procs if not p["zombie"]]
    protected = sum(1 for p in alive if p["beschermd"])
    piece = [f"{len(alive)} processes, {protected} of them protected"]
    if alive:
        heavy = max(alive, key=lambda p: (p["cpu"], p["mb"]))
        piece.append(
            f"heaviest: {heavy['naam']} (pid {heavy['pid']}, {heavy['cpu']}% cpu, "
            f"{heavy['mb']} MB, {heavy['gebruiker']})"
        )
    if boxes:
        piece.append(f"{len(boxes)} workbench box(es) busy")
    else:
        piece.append("no workbench busy")
    if not service["bereikbaar"]:
        piece.append("workbench service not reachable")
    return ". ".join(piece) + "."


def boxes_human(view):
    service = view["dienst"]
    boxes = view["boxen"]
    lines = []
    if service["bereikbaar"]:
        lines.append(f"Workbench service reachable ({service['url']}).")
    else:
        lines.append(f"Workbench service not reachable ({service['url']}): {service['melding']}")
    if not boxes:
        lines.append("No workbench boxes running right now.")
        return "\n".join(lines)
    lines.append(f"{len(boxes)} box(es) busy:")
    for b in boxes:
        command = b["commando"] or "(no command)"
        if len(command) > 70:
            command = command[:67] + "..."
        lines.append(f"  {b['leeftijd_tekst']:>8}  {b['map']}  {command}")
    return "\n".join(lines)


def stop_action(pid, hard, ja):
    try:
        st = read_stat(pid)
    except OSError:
        print(f"pid {pid} does not exist (anymore).")
        return 1
    name = st["name"]
    cmd = read_cmd(pid, name)
    tree = own_tree()
    reason = protected_reason(pid, st["ppid"], name, cmd, tree, st["status"])
    if reason:
        print(f"pid {pid} ({name}) is protected: {reason}. I will not stop it.")
        return 1
    if not ja:
        print(
            f"Stop pid {pid} ({name}, {cmd[:60]})? "
            f"Confirm with: processes stop {pid}{' --hard' if hard else ''} --ja"
        )
        return 0
    sig = signal.SIGKILL if hard else signal.SIGTERM
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        print(f"pid {pid} was already gone.")
        return 0
    except PermissionError:
        print(f"pid {pid} ({name}) is not mine; I am not allowed to stop it.")
        return 1
    print(f"pid {pid} ({name}) {'hard stopped' if hard else 'asked to stop'}.")
    return 0


def read_flags(args):
    return (
        "--json" in args,
        "--all" in args or "--alles" in args,
        "--hard" in args,
        "--ja" in args,
    )


def main():
    args = sys.argv[1:]
    if args and args[0] in ("help", "-h", "--help"):
        print(__doc__.strip())
        return 0
    as_json, everything, hard, ja = read_flags(args)
    plain = [a for a in args if not a.startswith("--")]
    sub = plain[0].lower() if plain else "all"

    if sub == "stop":
        if len(plain) < 2 or not plain[1].isdigit():
            print("Usage: processes stop <pid> [--hard] [--ja]")
            return 1
        return stop_action(int(plain[1]), hard, ja)

    if sub in ("procs", "processen"):
        procs = collect_procs()
        if as_json:
            print(json.dumps({"procs": procs}, ensure_ascii=False))
        else:
            print(procs_human(procs, everything))
        return 0

    if sub in ("boxes", "boxen", "werkplekken"):
        view = boxes_view()
        if as_json:
            print(json.dumps(view, ensure_ascii=False))
        else:
            print(boxes_human(view))
        return 0

    if sub not in ("all", "alles", "processes", "process-monitor"):
        print(f"Unknown: {sub}. Use: processes [procs|boxes|stop <pid>|help]")
        return 1

    procs = collect_procs()
    view = boxes_view()
    if as_json:
        print(json.dumps({
            "tijd": int(time.time()),
            "procs": procs,
            "boxen": view["boxen"],
            "dienst": view["dienst"],
        }, ensure_ascii=False))
    else:
        print(summary(procs, view["boxen"], view["dienst"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
