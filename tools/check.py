#!/usr/bin/env python3
"""Check the plugins in this repository against the rules of https://plugins.okayiris.com/docs.md.

  python3 tools/check.py              every folder under plugins/
  python3 tools/check.py weather      only these

It checks what the marketplace review and the style gate check: the manifest, the files it names, one
flat folder under 6 MB, lang-en.json with every text a window uses, the settings form, and the design
rules for .jsx (only the kit, only the house colours, no fixed sizes). Exit code 1 when anything fails.
"""
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "plugins")
PERMISSIONS = {"internet", "files", "secrets", "phone", "voice", "messages"}
CATEGORIES = {"communication", "finance", "productivity", "home", "media", "knowledge", "developer", "other"}
FIELDS = {"name", "version", "author", "description", "permissions", "commands", "slash", "window", "screen",
          "routes", "database", "category", "icon", "screenshots", "usage", "provides", "setup", "oauth",
          "initiative", "actions", "kind"}
SETTING_TYPES = {"text", "number", "toggle", "choice", "list"}
# Files a plugin makes for itself once it runs; never part of what is published.
RUNTIME = re.compile(r"^(values\.json|data\.db.*|\..*|.*\.tmp|__pycache__)$")
MAX_BYTES = 6 * 1024 * 1024
# Icon names seen drawing in published plugins and in the guide. Another name is only a warning: it may
# exist in the kit, but nothing shows it does.
KNOWN_ICONS = {"calendar", "card", "chart", "clock", "database", "euro", "mail", "meter", "server", "stop",
               "kruis", "pakket", "schild", "vernieuw"}


def check(folder):
    problems = []
    name = os.path.basename(folder)
    bad = problems.append

    files = [f for f in os.listdir(folder) if not RUNTIME.match(f)]
    for f in files:
        if os.path.isdir(os.path.join(folder, f)):
            bad(f"{f}/ is a folder; a plugin is one flat folder")
    size = sum(os.path.getsize(os.path.join(folder, f)) for f in files if os.path.isfile(os.path.join(folder, f)))
    if size > MAX_BYTES:
        bad(f"the folder is {size / 1024 / 1024:.1f} MB, more than 6 MB")

    try:
        with open(os.path.join(folder, "plugin.json"), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as exc:
        return [f"plugin.json: {exc}"]

    for key in ("name", "version", "author", "description", "permissions"):
        if key not in m:
            bad(f"plugin.json has no {key}")
    for key in m:
        if key not in FIELDS:
            bad(f"plugin.json has an unknown field {key}")
    if m.get("name") != name:
        bad(f"name {m.get('name')!r} is not the folder name {name!r}")
    if not re.fullmatch(r"[a-z0-9-]{1,40}", name):
        bad("the name is not lowercase letters, digits and - (at most 40)")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(m.get("version", ""))):
        bad("version is not three numbers like 1.0.0")
    perms = m.get("permissions")
    if not isinstance(perms, list) or not set(perms) <= PERMISSIONS:
        bad(f"permissions must be a list out of {sorted(PERMISSIONS)}")
    if "category" in m and m["category"] not in CATEGORIES:
        bad(f"category {m['category']!r} is not one of {sorted(CATEGORIES)}")

    commands = m.get("commands") or {}
    for cmd, file in commands.items():
        path = os.path.join(folder, file)
        if not os.path.isfile(path):
            bad(f"command {cmd}: {file} is missing")
            continue
        # The #! line is the rule; the executable bit is not kept by the marketplace, so it is not checked.
        with open(path, "rb") as f:
            if not f.read(2) == b"#!":
                bad(f"command {cmd}: {file} does not start with a #! line")
    for cmd in m.get("slash") or {}:
        if cmd not in commands:
            bad(f"slash {cmd} is not one of the commands")
    for key in ("window", "screen"):
        if key in m:
            if not str(m[key]).endswith(".jsx") or not os.path.isfile(os.path.join(folder, m[key])):
                bad(f"{key} {m[key]} is not a .jsx file in the folder")
    if "icon" in m and not os.path.isfile(os.path.join(folder, m["icon"])):
        bad(f"icon {m['icon']} is missing")
    for shot in m.get("screenshots") or []:
        if not os.path.isfile(os.path.join(folder, shot)):
            bad(f"screenshot {shot} is missing")
    if m.get("database") and not os.path.isfile(os.path.join(folder, "schema.sql")):
        bad("database is on but there is no schema.sql")
    for route, spec in (m.get("routes") or {}).items():
        if not re.fullmatch(r"[a-z0-9-]+", route):
            bad(f"route {route} is not one word")
        if spec.get("command") not in commands:
            bad(f"route {route}: its command is not one of the plugin's own")
        if not os.path.isfile(os.path.join(folder, spec.get("page", ""))):
            bad(f"route {route}: page {spec.get('page')} is missing")

    if not os.path.isfile(os.path.join(folder, "README.md")):
        bad("there is no README.md for the marketplace page")

    # Languages
    lang = {}
    try:
        with open(os.path.join(folder, "lang-en.json"), encoding="utf-8") as f:
            lang = json.load(f)
    except OSError:
        bad("lang-en.json is missing")
    except ValueError as exc:
        bad(f"lang-en.json: {exc}")
    if lang and lang.get("description") != m.get("description"):
        bad("lang-en.json description differs from plugin.json")
    if lang and (lang.get("slash") or {}) != (m.get("slash") or {}):
        bad("lang-en.json slash differs from plugin.json")
    texts = lang.get("texts") or {}
    for f in files:
        if re.fullmatch(r"lang-[A-Za-z-]+\.json", f) and f != "lang-en.json":
            try:
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    other = json.load(fh)
            except ValueError as exc:
                bad(f"{f}: {exc}")
                continue
            for key in other.get("texts") or {}:
                if key not in texts:
                    bad(f"{f} has text {key} that lang-en.json lacks")

    # Settings
    if os.path.isfile(os.path.join(folder, "settings.json")):
        try:
            with open(os.path.join(folder, "settings.json"), encoding="utf-8") as f:
                s = json.load(f)
            if s.get("command") not in commands:
                bad("settings.json command is not one of the commands")
            fields = s.get("fields") or []
            if len(fields) > 20:
                bad("settings.json has more than 20 fields")
            for fl in fields:
                if not re.fullmatch(r"[a-z0-9_]+", fl.get("key", "")):
                    bad(f"settings key {fl.get('key')!r} is not lowercase letters, digits and _")
                if fl.get("type") not in SETTING_TYPES:
                    bad(f"settings {fl.get('key')}: type {fl.get('type')!r} is not known")
                if fl.get("type") == "choice" and not fl.get("options"):
                    bad(f"settings {fl.get('key')}: a choice needs options")
        except ValueError as exc:
            bad(f"settings.json: {exc}")

    # Design rules for every .jsx
    for f in files:
        if f.endswith(".jsx"):
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                problems += [f"{f}: {p}" for p in check_jsx(fh.read(), texts)]

    # No secrets
    for f in files:
        path = os.path.join(folder, f)
        if f.endswith((".py", ".js", ".sh", ".json", ".md", ".jsx")) and os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
            if re.search(r"(sk_live_|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})", body):
                bad(f"{f} looks like it holds a key")
    return problems


def check_jsx(src, texts):
    problems = []
    # Everything you press is a Button. Text fields, dates and times have no kit component, so a form
    # may use <input>, <select> and <textarea>.
    if re.search(r"<\s*(button|a)\b", src):
        problems.append("a bare <button> or <a>; everything you press is a Button")
    if re.search(r"<div[^>]*onClick", src):
        problems.append("a clickable <div>; use a Button")
    if re.search(r"position\s*:\s*['\"]?fixed", src):
        problems.append("position: fixed")
    if re.search(r"outline\s*:\s*['\"]?none|transition\s*:\s*['\"]?none", src):
        problems.append("outline: none or transition: none")
    for value in re.findall(r"font-?family\s*[:=]\s*['\"]?([^'\";,}]+)", src, re.I):
        if value.strip().lower() != "inherit":
            problems.append(f"an own font ({value.strip()})")
    if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", src):
        problems.append("a colour that is not a house colour var(--...)")
    for px in re.findall(r"(\d+)\s*px", src):
        if int(px) > 64:
            problems.append(f"a fixed size of {px}px (above 64px)")
    if "—" in src or "–" in src:
        problems.append("an em or en dash")
    for ch in src:
        if unicodedata.category(ch) == "So" and ord(ch) > 0x2000:
            problems.append(f"an emoji or symbol {ch!r}")
            break
    if not re.search(r"export\s+default", src):
        problems.append("no default export")
    for key in re.findall(r"\btext\(\s*[\"']([^\"']+)[\"']", src):
        if key not in texts:
            problems.append(f"text {key!r} is not in lang-en.json")
    return problems


def icon_warnings(src):
    names = set(re.findall(r'\b(?:icon|icoon|name|naam)=\{?"([a-z0-9-]+)"', src))
    return sorted(names - KNOWN_ICONS)


def main(argv):
    names = argv or sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)))
    failed = 0
    commands = {}
    for name in names:
        folder = os.path.join(ROOT, name)
        problems = check(folder) if os.path.isdir(folder) else [f"there is no plugins/{name}"]
        try:
            with open(os.path.join(folder, "plugin.json"), encoding="utf-8") as f:
                for cmd in json.load(f).get("commands") or {}:
                    if cmd in commands:
                        problems.append(f"command {cmd} is also in {commands[cmd]}")
                    commands[cmd] = name
        except (OSError, ValueError):
            pass
        for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            if f.endswith(".jsx"):
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    unknown = icon_warnings(fh.read())
                if unknown:
                    print(f"note {name}: {f} uses icon names no published plugin shows: {', '.join(unknown)}")
        if problems:
            failed += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"     {p}")
        else:
            print(f"ok   {name}")
    print(f"{len(names) - failed} of {len(names)} plugins pass.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
