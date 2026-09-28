#!/usr/bin/env python3
"""A stand-in for the house vault (`kluis` / `vault`), for the test environment.

  kluis lijst                               the items: SIM_VAULT="name|domain, name|domain"
  kluis vraag <item> --domein <d> <what>    says it is saved (and adds it for this run)
  kluis doe <item> <METHOD> <url> [body] [--kop "Header: {g}"]...
  vault list / vault ask / vault call ... --header ...   the English spelling from the guide

`doe` answers like the real vault: a first line `status <code>`, then the body.
  SIM_HTTP=replay   from the cassette, found by the request with {g} still in it
  SIM_HTTP=record   the real call, with the key from IRIS_KEY_<ITEM> (like IRIS_KEY_TODOIST);
                    the cassette keeps the request with {g}, never the key
  SIM_HTTP=live     the real call, nothing kept
Every call is written to SIM_VAULT_LOG, so a test can check what a plugin asked the vault to do.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from sitecustomize import key_of, _encode, _decode, _real_urlopen  # noqa: E402  (same cassette format)

MODE = os.environ.get("SIM_HTTP", "replay")
CASSETTE = os.environ.get("SIM_CASSETTE", "")


def items():
    out = []
    for part in os.environ.get("SIM_VAULT", "").split(","):
        name, _, domain = part.strip().partition("|")
        if name:
            out.append((name, domain or name))
    extra = os.path.join(os.environ.get("HOME", "."), ".sim-vault-added")
    if os.path.exists(extra):
        for line in open(extra, encoding="utf-8"):
            name, _, domain = line.strip().partition("|")
            if name and all(n != name for n, _ in out):
                out.append((name, domain))
    return out


def log(args):
    path = os.environ.get("SIM_VAULT_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(args) + "\n")


def tape():
    if CASSETTE and os.path.exists(CASSETTE):
        with open(CASSETTE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def fill(text, key):
    return text.replace("{g:base64}", base64.b64encode(key.encode()).decode()).replace("{g}", key)


def do(args):
    if len(args) < 3:
        sys.exit("vault: doe <item> <METHOD> <url> [body] [--kop header]...")
    item, method, url = args[0], args[1].upper(), args[2]
    rest, headers, body = args[3:], [], None
    i = 0
    while i < len(rest):
        if rest[i] in ("--kop", "--header") and i + 1 < len(rest):
            headers.append(rest[i + 1])
            i += 2
        elif rest[i] in ("--data", "--body") and i + 1 < len(rest):
            body = rest[i + 1]
            i += 2
        else:
            body = rest[i] if body is None else body
            i += 1
    if item not in [n for n, _ in items()]:
        sys.exit(f"vault: there is no item called {item}")
    raw_body = body.encode() if body is not None else None
    key = key_of(method, url, raw_body)
    if MODE == "replay":
        entry = tape().get("http", {}).get(key)
        if entry is None:
            misses = os.environ.get("SIM_MISSES")
            if misses:
                with open(misses, "a", encoding="utf-8") as f:
                    f.write("vault " + key + "\n")
            sys.exit(f"vault: not in the cassette: {key}")
        print(f"status {entry['status']}")
        sys.stdout.write(_decode(entry).decode("utf-8", "replace"))
        return
    secret = os.environ.get("IRIS_KEY_" + item.upper().replace("-", "_"))
    stub = os.environ.get("SIM_VAULT_STUB")
    if not secret and stub and MODE == "record":
        # No key: a stub made from the service's documentation answers, and the cassette says so.
        import importlib.util
        spec = importlib.util.spec_from_file_location("stub", stub)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        status, payload = mod.answer(item, method, url, body)
        raw = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
        data = tape()
        data["synthetic"] = True
        entry = {"status": status, "url": url, "type": "application/json"}
        entry.update(_encode(raw))
        data.setdefault("http", {})[key] = entry
        data["http"] = dict(sorted(data["http"].items()))
        with open(CASSETTE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(CASSETTE + ".tmp", CASSETTE)
        print(f"status {status}")
        sys.stdout.write(raw.decode())
        return
    if not secret:
        sys.exit(f"vault: no key for {item}; set IRIS_KEY_{item.upper().replace('-', '_')} for a live run")
    req = urllib.request.Request(fill(url, secret), data=raw_body, method=method)
    for h in headers:
        name, _, value = h.partition(":")
        req.add_header(name.strip(), fill(value.strip(), secret))
    try:
        # The real urlopen, not the recording one: the recorder would keep the address with the key in it.
        with _real_urlopen(req, timeout=60) as resp:
            raw, status, ctype = resp.read(), resp.status, resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw, status, ctype = exc.read(), exc.code, exc.headers.get("Content-Type", "") if exc.headers else ""
    if secret.encode() in raw:
        raw = raw.replace(secret.encode(), b"{g}")        # a key never lands in a cassette or a log
    if MODE == "record" and status != 429 and status < 500:
        data = tape()
        entry = {"status": status, "url": url, "type": ctype}
        entry.update(_encode(raw))
        data.setdefault("http", {})[key] = entry
        data["http"] = dict(sorted(data["http"].items()))
        with open(CASSETTE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(CASSETTE + ".tmp", CASSETTE)
    print(f"status {status}")
    sys.stdout.write(raw.decode("utf-8", "replace"))


def main(argv):
    log(argv)
    if not argv:
        sys.exit("vault: lijst, vraag, doe")
    cmd, rest = argv[0], argv[1:]
    if cmd in ("lijst", "list"):
        found = items()
        if not found:
            print("de kluis is leeg")
        for name, domain in found:
            print(f"{name}  owner  {domain}")
    elif cmd in ("vraag", "ask"):
        name = rest[0] if rest else "item"
        domain = rest[rest.index("--domein") + 1] if "--domein" in rest else (
            rest[rest.index("--domain") + 1] if "--domain" in rest else name)
        with open(os.path.join(os.environ.get("HOME", "."), ".sim-vault-added"), "a", encoding="utf-8") as f:
            f.write(f"{name}|{domain}\n")
        print(f'saved in the vault as "{name}".')
    elif cmd in ("doe", "call"):
        do(rest)
    else:
        sys.exit(f"vault: unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
