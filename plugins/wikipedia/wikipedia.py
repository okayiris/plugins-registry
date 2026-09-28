#!/usr/bin/env python3
"""Look things up on Wikipedia, in the language you choose. No key and no account.

  wikipedia <subject>                   the short summary of the article that fits best
  wikipedia search <text>               the articles that match, with a line each
  wikipedia more <subject>              the opening of the article, longer than the summary
  wikipedia today                       what happened on this day in history
  wikipedia random                      a random article
  wikipedia settings                    the values as JSON
  wikipedia settings set <key> <value>  change one value (language)

Every answer ends with the link to the article, so the owner can read on.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
DEFAULT = {"language": "en"}
UA = "Iris-wikipedia/1.0 (https://plugins.okayiris.com/apps/wikipedia)"


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
    tmp = VALUES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, VALUES_FILE)


def lang():
    value = values()["language"].strip().lower()
    return value if re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", value) else "en"


def get(url, missing_ok=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and missing_ok:
            return None
        if exc.code == 429:
            sys.exit("Wikipedia asks to slow down. Try again in a minute.")
        sys.exit(f"Wikipedia answered with status {exc.code}.")
    except (OSError, ValueError):
        sys.exit("Wikipedia did not answer. Try again in a minute.")


def rest(path, missing_ok=False):
    return get(f"https://{lang()}.wikipedia.org/api/rest_v1/{path}", missing_ok)


def action(**params):
    params.update({"format": "json", "formatversion": "2"})
    return get(f"https://{lang()}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params))


def title_of(text):
    return urllib.parse.quote(text.strip().replace(" ", "_"), safe="")


def best_title(subject):
    """The article the subject most likely means: the exact title, else the first search hit."""
    found = action(action="query", list="search", srsearch=subject, srlimit=1, srprop="")
    hits = ((found or {}).get("query") or {}).get("search") or []
    return hits[0]["title"] if hits else None


def link(summary):
    return ((summary.get("content_urls") or {}).get("desktop") or {}).get("page", "")


def plain(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def print_summary(s):
    print(s["title"] + (f", {s['description']}" if s.get("description") else ""))
    print(s.get("extract") or "No summary.")
    if link(s):
        print(link(s))


# --- commands -------------------------------------------------------------------------------------

def summary_for(subject):
    s = rest(f"page/summary/{title_of(subject)}", missing_ok=True)
    if not s or s.get("type") == "disambiguation":
        title = best_title(subject)
        if not title:
            sys.exit(f"Wikipedia has no article about {subject}.")
        s = rest(f"page/summary/{title_of(title)}", missing_ok=True)
        if not s:
            sys.exit(f"Wikipedia has no article about {subject}.")
    return s


def cmd_summary(args):
    subject = " ".join(args).strip()
    if not subject:
        sys.exit("wikipedia <subject>")
    s = summary_for(subject)
    if s.get("type") == "disambiguation":
        print(f"{s['title']} can mean several things. Try `wikipedia search {subject}`.")
        return
    print_summary(s)


def cmd_more(args):
    subject = " ".join(args).strip()
    if not subject:
        sys.exit("wikipedia more <subject>")
    s = summary_for(subject)
    data = action(action="query", prop="extracts", exintro=1, explaintext=1, redirects=1, titles=s["title"])
    pages = ((data or {}).get("query") or {}).get("pages") or []
    text = (pages[0].get("extract") if pages else "") or s.get("extract") or ""
    if len(text) > 2500:
        text = text[:2500].rsplit(". ", 1)[0] + "."
    print(s["title"])
    print(text.strip())
    if link(s):
        print(link(s))


def cmd_search(args):
    text = " ".join(args).strip()
    if not text:
        sys.exit("wikipedia search <text>")
    data = action(action="query", list="search", srsearch=text, srlimit=8, srprop="snippet")
    hits = ((data or {}).get("query") or {}).get("search") or []
    if not hits:
        print(f"Nothing on Wikipedia for {text}.")
        return
    print(f"On Wikipedia for {text}:")
    for h in hits:
        snippet = plain(h.get("snippet"))
        print(f"  {h['title']}" + (f": {snippet[:140]}" if snippet else ""))


def cmd_today():
    today = date.today()
    data = rest(f"feed/onthisday/selected/{today.month:02d}/{today.day:02d}", missing_ok=True)
    events = (data or {}).get("selected") or []
    if not events:
        data = rest(f"feed/onthisday/events/{today.month:02d}/{today.day:02d}", missing_ok=True)
        events = (data or {}).get("events") or []
    if not events:
        sys.exit("Wikipedia has no list of this day in this language. Try the language setting en.")
    print(f"On {today.strftime('%d %B')}:")
    for e in sorted(events[:8], key=lambda e: e.get("year", 0)):
        print(f"  {e.get('year', '')}  {plain(e.get('text'))}")


def cmd_random():
    s = rest("page/random/summary")
    print_summary(s)


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 3 or args[0] != "set" or args[1] != "language":
        sys.exit("wikipedia settings set language <code, like en or nl>")
    value = args[2].strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", value):
        sys.exit("A language is its Wikipedia code: en, nl, de, fr, es and so on.")
    keep("language", value)
    print(f"Reading {value}.wikipedia.org from now on.")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif argv[0] == "search":
        cmd_search(argv[1:])
    elif argv[0] == "more":
        cmd_more(argv[1:])
    elif argv[0] == "today" and len(argv) == 1:
        cmd_today()
    elif argv[0] == "random" and len(argv) == 1:
        cmd_random()
    elif argv[0] == "settings":
        cmd_settings(argv[1:])
    else:
        cmd_summary(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
