#!/usr/bin/env python3
"""Translate text with your own DeepL key, free or Pro.

  translate <text>                      into your usual language (it works out what the text is in)
  translate to <language> <text>        into another language, like: translate to german Good morning
  translate formal to <language> <text> the polite form, where the language has one
  translate usage                       how many characters are used this month, of how many
  translate languages                   the languages you can translate into
  translate key / translate key ask     is there a key in the vault / paste one in
  translate settings                    the values as JSON
  translate settings set <key> <value>  change one value (target, plan)

The DeepL key stays in the vault. Every call is made by the vault, which fills in the key as {g}; this
script never sees it. A free key uses api-free.deepl.com, a Pro key api.deepl.com: the plugin tries the
other one by itself when DeepL says the key belongs there.
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
ITEM = "deepl"
HOSTS = {"free": "https://api-free.deepl.com/v2/", "pro": "https://api.deepl.com/v2/"}
DEFAULT = {"target": "EN-GB", "plan": "free"}
NAMES = {
    "english": "EN-GB", "british": "EN-GB", "american": "EN-US", "dutch": "NL", "nederlands": "NL",
    "german": "DE", "deutsch": "DE", "french": "FR", "spanish": "ES", "italian": "IT", "portuguese": "PT-PT",
    "brazilian": "PT-BR", "polish": "PL", "swedish": "SV", "danish": "DA", "norwegian": "NB", "finnish": "FI",
    "czech": "CS", "greek": "EL", "hungarian": "HU", "romanian": "RO", "turkish": "TR", "ukrainian": "UK",
    "russian": "RU", "japanese": "JA", "korean": "KO", "chinese": "ZH-HANS", "indonesian": "ID",
    "arabic": "AR", "bulgarian": "BG", "estonian": "ET", "latvian": "LV", "lithuanian": "LT",
    "slovak": "SK", "slovenian": "SL",
}
FORMAL = {"DE", "FR", "IT", "ES", "NL", "PL", "PT-PT", "PT-BR", "JA", "RU"}


def fail(msg):
    sys.exit(msg)


def values():
    out = dict(DEFAULT)
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            kept = json.load(f)
        if isinstance(kept, dict):
            out.update({str(k): str(v) for k, v in kept.items()})
    except (OSError, ValueError):
        pass
    return out


def keep(key, value):
    data = {}
    try:
        with open(VALUES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data[key] = value
    with open(VALUES_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def language(text):
    t = text.strip().lower()
    if t in NAMES:
        return NAMES[t]
    if re.fullmatch(r"[a-z]{2}(-[a-z]{2,4})?", t):
        code = t.upper()
        return {"EN": "EN-GB", "PT": "PT-PT", "ZH": "ZH-HANS"}.get(code, code)
    return None


# --- the vault ------------------------------------------------------------------------------------

def vault_bin():
    p = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN")
    return p or shutil.which("kluis") or shutil.which("vault")


def key_item():
    exe = vault_bin()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    items = []
    for line in r.stdout.splitlines():
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p]
        if len(parts) >= 3 and not line.strip().startswith("de kluis"):
            items.append((parts[0], parts[2].strip().lower()))
    for name, _ in items:
        if name == ITEM:
            return name
    for name, domain in items:
        if domain.endswith("deepl.com"):
            return name
    return None


def call_once(plan, method, path, body):
    item = key_item()
    if not item:
        fail("There is no DeepL key in the vault yet. Say: translate key ask. "
             "A free key is at deepl.com/pro-api, under Account, API keys.")
    cmd = [vault_bin(), "doe", item, method, HOSTS[plan] + path]
    if body is not None:
        cmd += [json.dumps(body), "--kop", "Content-Type: application/json"]
    cmd += ["--kop", "Authorization: DeepL-Auth-Key {g}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        fail("DeepL did not answer in time.")
    first, _, rest = (r.stdout or "").partition("\n")
    m = re.match(r"status\s+(\d+)", first.strip())
    if not m:
        fail((r.stderr or r.stdout or "").strip() or "The vault refused the call.")
    return int(m.group(1)), rest.strip()


def call(method, path, body=None):
    plan = values()["plan"] if values()["plan"] in HOSTS else "free"
    status, text = call_once(plan, method, path, body)
    if status == 403 and "wrong endpoint" in text.lower():
        other = "pro" if plan == "free" else "free"
        status, text = call_once(other, method, path, body)
        if status < 400:
            keep("plan", other)
    if status == 403:
        fail("DeepL refused the key. Put a fresh one in the vault with: translate key ask.")
    if status == 456:
        fail("The DeepL quota for this month is used up.")
    if status == 429:
        fail("DeepL asks to slow down. Try again in a moment.")
    if status >= 400:
        fail(f"DeepL answered with status {status}.")
    try:
        return json.loads(text) if text else {}
    except ValueError:
        fail("DeepL gave an answer I could not read.")


# --- commands -------------------------------------------------------------------------------------

def cmd_translate(args):
    formal = False
    if args and args[0].lower() == "formal":
        formal, args = True, args[1:]
    target = language(values()["target"]) or "EN-GB"
    if len(args) >= 2 and args[0].lower() in ("to", "into", "naar"):
        target = language(args[1])
        if not target:
            fail(f"I do not know the language {args[1]}. `translate languages` shows them.")
        args = args[2:]
    text = " ".join(args).strip()
    if not text:
        fail("translate [to <language>] <text>")
    body = {"text": [text], "target_lang": target}
    if formal and target in FORMAL:
        body["formality"] = "prefer_more"
    data = call("POST", "translate", body)
    out = (data.get("translations") or [{}])[0]
    source = out.get("detected_source_language", "")
    if source and target.startswith(source):
        print(f"That is already in {target}. Say `translate to <language>` for another one.")
        return
    print(out.get("text", ""))
    print(f"({source or '?'} to {target})")


def cmd_usage():
    data = call("GET", "usage")
    used, limit = data.get("character_count", 0), data.get("character_limit") or 0
    if limit:
        print(f"{used:,} of {limit:,} characters used this month ({used * 100 // limit}%).")
    else:
        print(f"{used:,} characters used this month.")


def cmd_languages():
    data = call("GET", "languages?type=target")
    print("You can translate into: " + ", ".join(f"{l['name']} ({l['language']})" for l in data) + ".")


def cmd_key(args):
    if args and args[0] == "ask":
        exe = vault_bin()
        if not exe:
            fail("The vault is not on this system.")
        print("A window opens to paste your DeepL API key; it goes straight into the vault.")
        r = subprocess.run([exe, "vraag", ITEM, "--domein", "deepl.com", "DeepL API key"],
                           capture_output=True, text=True, timeout=240)
        if r.returncode != 0:
            fail((r.stderr or r.stdout).strip() or "The vault did not save a key.")
        print((r.stdout or "").strip() or "Saved in the vault.")
        return
    item = key_item()
    print(f'A DeepL key is in the vault as "{item}".' if item else "No DeepL key in the vault yet. Say: translate key ask.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values()))
        return
    if len(args) < 3 or args[0] != "set":
        fail("translate settings set <target|plan> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "target":
        code = language(value)
        if not code:
            fail(f"I do not know the language {value}.")
        keep("target", code)
        print(f"Translating into {code} unless you say otherwise.")
    elif key == "plan":
        if value.lower() not in HOSTS:
            fail("The plan is free or pro.")
        keep("plan", value.lower())
        print(f"Using DeepL {value.lower()}.")
    else:
        fail(f"There is no setting called {key}. Use target or plan.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("", "-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "usage" and not rest:
        cmd_usage()
    elif cmd == "languages" and not rest:
        cmd_languages()
    elif cmd == "key" and len(rest) <= 1:
        cmd_key(rest)
    elif cmd == "settings":
        cmd_settings(rest)
    else:
        cmd_translate(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
