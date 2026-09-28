#!/usr/bin/env python3
"""Search for Iris: web search with your own key, through Brave Search or Google Programmable Search.

  search "<query>" [-n 5]        search the web
  search provider brave|google   which service to use
  search key ask brave|google    ask for that API key (it goes straight into the vault)
  search key                     which vault items are used, never the keys themselves
  search engine "<cx>"           the Google Programmable Search engine id (not a secret)

Both keys stay in the vault. For Brave the vault makes the call with the key in the
X-Subscription-Token header; for Google it goes in the URL as {g}. Either way this tool never
sees the key. Set up with: search key ask brave   (or google)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

HERE = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(HERE, ".state.json")

BRAVE = "https://api.search.brave.com/res/v1/web/search"
GOOGLE = "https://www.googleapis.com/customsearch/v1"

BRAVE_ITEM = "search-brave"
BRAVE_DOMAIN = "api.search.brave.com"
GOOGLE_ITEM = "search-google"
GOOGLE_DOMAIN = "www.googleapis.com"


def fail(text):
    print(f"search: {text}")
    sys.exit(1)


# ---------------------------------------------------------------- state

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE)


# ---------------------------------------------------------------- vault

def vault_bin():
    p = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN")
    if p:
        return p
    return shutil.which("kluis") or shutil.which("vault")


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
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        parts = [p for p in re.split(r"\s{2,}", line) if p]
        if len(parts) >= 3:
            items.append({"name": parts[0], "user": parts[1], "domain": parts[2]})
    return items


def item_for(name, domain):
    items = vault_items()
    for it in items:
        if it["name"] == name:
            return it["name"]
    for it in items:
        if it["domain"].strip().lower() == domain:
            return it["name"]
    return None


def brave_item():
    return item_for(BRAVE_ITEM, BRAVE_DOMAIN)


def google_item():
    return item_for(GOOGLE_ITEM, GOOGLE_DOMAIN)


def vault_ask(name, domain, what):
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system.")
    try:
        r = subprocess.run([exe, "vraag", name, "--domein", domain, what],
                           capture_output=True, text=True, timeout=220)
    except subprocess.TimeoutExpired:
        fail("the vault did not answer in time.")
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        fail((r.stderr or "").strip() or out or "the vault did not save it.")
    print(out or f'saved in the vault as "{name}".')


def vault_call(item, method, url, headers=None, timeout=60):
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system.")
    cmd = [exe, "doe", item, method, url]
    for h in headers or []:
        cmd += ["--kop", h]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        fail("the vault did not answer in time.")
    except OSError as exc:
        fail(str(exc))
    out = r.stdout or ""
    if not out.strip():
        fail((r.stderr or "").strip() or "no answer from the vault.")
    first, _, rest = out.partition("\n")
    status = 0
    m = re.match(r"status\s+(\d+)", first.strip())
    if m:
        status = int(m.group(1))
    return status, rest


# ---------------------------------------------------------------- providers

def search_brave(query, n):
    item = brave_item()
    if not item:
        fail("no Brave Search API key in the vault. Run: search key ask brave")
    url = BRAVE + "?" + urllib.parse.urlencode({"q": query, "count": n})
    status, text = vault_call(item, "GET", url, headers=["X-Subscription-Token: {g}"])
    if status == 401 or status == 422:
        fail("Brave refused the key. Put a fresh one in the vault with: search key ask brave")
    if status >= 400:
        fail(f"Brave answered with status {status}.")
    try:
        data = json.loads(text)
    except ValueError:
        fail("Brave returned an unreadable answer.")
    rows = ((data.get("web") or {}).get("results")) or []
    return [{"title": r.get("title", "?"), "url": r.get("url", ""),
             "snippet": r.get("description", "")} for r in rows[:n]]


def search_google(query, n):
    item = google_item()
    if not item:
        fail("no Google Programmable Search API key in the vault. Run: search key ask google")
    cx = str(load_state().get("cx") or "").strip()
    if not cx:
        fail('no search engine id yet. Set it with: search engine "<cx>"')
    url = GOOGLE + "?" + "&".join([
        "key={g}",
        "cx=" + urllib.parse.quote(cx),
        "q=" + urllib.parse.quote(query),
        "num=" + str(min(10, n)),
    ])
    status, text = vault_call(item, "GET", url)
    if status == 403:
        fail("Google refused the key or the engine id.")
    if status >= 400:
        fail(f"Google answered with status {status}.")
    try:
        data = json.loads(text)
    except ValueError:
        fail("Google returned an unreadable answer.")
    rows = data.get("items") or []
    return [{"title": r.get("title", "?"), "url": r.get("link", ""),
             "snippet": r.get("snippet", "")} for r in rows[:n]]


def active_provider():
    st = load_state()
    chosen = st.get("provider")
    if chosen in ("brave", "google"):
        return chosen
    if brave_item():
        return "brave"
    if google_item():
        return "google"
    return None


# ---------------------------------------------------------------- commands

def cmd_search(args):
    n = 5
    free = []
    i = 0
    while i < len(args):
        if args[i] in ("-n", "--n") and i + 1 < len(args):
            try:
                n = max(1, min(20, int(args[i + 1])))
            except ValueError:
                fail("-n needs a number")
            i += 2
            continue
        free.append(args[i])
        i += 1
    query = " ".join(free).strip()
    if not query:
        fail('use: search "<query>" [-n 5]')
    provider = active_provider()
    if not provider:
        fail('no search key in the vault yet. Run `search key ask brave` or `search key ask google`.')
    try:
        rows = search_brave(query, n) if provider == "brave" else search_google(query, n)
    except SystemExit:
        raise
    if not rows:
        print(f'No results for "{query}".')
        return
    for r in rows:
        print(r["title"])
        print(f"  {r['url']}")
        snippet = (r.get("snippet") or "").strip().replace("\n", " ")
        if snippet:
            print(f"  {snippet[:200]}")


def cmd_key(args):
    if args and args[0] == "ask":
        which = args[1] if len(args) > 1 else None
        if which not in ("brave", "google"):
            fail("use: search key ask brave   or   search key ask google")
        if which == "brave":
            print("A window opens to paste your Brave Search API key; it goes straight into the vault.")
            vault_ask(BRAVE_ITEM, BRAVE_DOMAIN, "Brave Search API key")
        else:
            print("A window opens to paste your Google Programmable Search API key; it goes straight into the vault.")
            vault_ask(GOOGLE_ITEM, GOOGLE_DOMAIN, "Google Programmable Search API key")
        st = load_state()
        if not st.get("provider"):
            st["provider"] = which
            save_state(st)
        return
    bravo = brave_item()
    google = google_item()
    if bravo:
        print(f'Brave:  vault item "{bravo}" for {BRAVE_DOMAIN}.')
    else:
        print("Brave:  none. Run: search key ask brave")
    if google:
        print(f'Google: vault item "{google}" for {GOOGLE_DOMAIN}.')
    else:
        print("Google: none. Run: search key ask google")


def cmd_provider(args):
    if not args or args[0] not in ("brave", "google"):
        fail("use: search provider brave   or   search provider google")
    st = load_state()
    st["provider"] = args[0]
    save_state(st)
    print(f"Provider set to {args[0]}.")


def cmd_engine(args):
    if not args:
        cx = str(load_state().get("cx") or "").strip()
        print(f'Search engine id: {cx}' if cx else 'No search engine id yet. Set it with: search engine "<cx>"')
        return
    st = load_state()
    st["cx"] = args[0].strip()
    save_state(st)
    print("Search engine id saved.")


def status():
    print("Search: web search through your own key, with Brave Search or Google Programmable Search.")
    print()
    provider = active_provider()
    if provider:
        print(f"Provider: {provider}")
    else:
        print("Provider: not set yet")
    cmd_key([])
    if load_state().get("cx"):
        print(f'Engine:  {load_state()["cx"]}')
    if not provider:
        print()
        print("You need a key from one of these, and it goes into the vault:")
        print("  Brave:  https://api-dashboard.search.brave.com/  (search key ask brave)")
        print("  Google: https://programmablesearchengine.google.com/  (search key ask google)")
        print()
        print("For Google, also create a search engine and copy its id (search engine \"<cx>\").")
    print()
    print('Try: search "<query>" -n 5')


def main():
    a = sys.argv[1:]
    if not a:
        status()
        return
    cmd = a[0]
    if cmd in ("help", "--help", "-h"):
        print(__doc__)
    elif cmd == "key":
        cmd_key(a[1:])
    elif cmd == "provider":
        cmd_provider(a[1:])
    elif cmd == "engine":
        cmd_engine(a[1:])
    else:
        cmd_search(a)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nsearch: stopped")
        sys.exit(1)
