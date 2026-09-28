#!/usr/bin/env python3
"""Podcasts: find a show, follow it, and hear what is new. Searched through the Apple Podcasts directory.

  podcasts                              new episodes of the shows you follow, the last seven days
  podcasts search <words>               shows that fit, numbered
  podcasts follow <number or name>      follow a show from the last search (or search and take the best)
  podcasts unfollow <name>              stop following one
  podcasts episodes <name> [count]      the latest episodes of one show you follow (5 by default)
  podcasts play <number>                the audio link of an episode from the last list
  podcasts list                         the shows you follow
  podcasts settings                     the values as JSON

The search goes to itunes.apple.com without a key; episodes come from each show's own RSS feed.
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
LAST_FILE = os.path.join(HERE, ".last.json")
SEARCH = "https://itunes.apple.com/search"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
DEFAULT = {"shows": "", "country": "NL"}


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
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def last(data=None):
    if data is not None:
        with open(LAST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
    try:
        with open(LAST_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Iris-podcasts/1.0"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(8_000_000)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"status {exc.code}")
        except OSError:
            if attempt == 2:
                raise


def search(words, limit=8):
    q = urllib.parse.urlencode({"term": words, "media": "podcast", "entity": "podcast", "limit": limit,
                                "country": values()["country"].lower()})
    try:
        data = json.loads(fetch(f"{SEARCH}?{q}"))
    except ValueError as exc:
        # Apple allows about twenty searches a minute and says so with a 403 (or 429), not with an error text.
        if str(exc) in ("status 403", "status 429"):
            sys.exit("The podcast directory asks to slow down. Try again in a minute.")
        sys.exit("The podcast directory gave an answer I could not read. Try again in a minute.")
    except OSError:
        sys.exit("The podcast directory did not answer. Try again in a minute.")
    return [{"name": r.get("collectionName", "?"), "by": r.get("artistName", ""), "feed": r.get("feedUrl", ""),
             "genre": r.get("primaryGenreName", ""), "count": r.get("trackCount", 0)}
            for r in data.get("results", []) if r.get("feedUrl")]


def followed():
    out = []
    for part in values()["shows"].split(","):
        name, _, feed = part.strip().rpartition("|")
        if feed.startswith("http"):
            out.append((name.strip(), feed.strip()))
    return out


def store(items):
    keep("shows", ", ".join(f"{n}|{f}" for n, f in items))


def plain(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def seconds(value):
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    parts = value.split(":")
    try:
        total = 0
        for p in parts:
            total = total * 60 + int(float(p))
        return total
    except ValueError:
        return None


def length(sec):
    if not sec:
        return ""
    h, m = divmod(round(sec / 60), 60)
    return f"{h} h {m} min" if h else f"{m} min"


def episodes(feed, show):
    try:
        root = ET.fromstring(fetch(feed))
    except (OSError, ValueError, ET.ParseError):
        return None
    out = []
    for item in root.iter("item"):
        enclosure = item.find("enclosure")
        stamp = item.findtext("pubDate")
        try:
            at = parsedate_to_datetime(stamp).timestamp() if stamp else 0
        except (TypeError, ValueError):
            at = 0
        out.append({"show": show, "title": plain(item.findtext("title")), "at": at,
                    "audio": enclosure.get("url") if enclosure is not None else "",
                    "length": length(seconds(item.findtext(ITUNES + "duration"))),
                    "about": plain(item.findtext("description") or item.findtext(ITUNES + "summary"))[:280]})
    out.sort(key=lambda e: e["at"], reverse=True)
    return out


def when(ts):
    if not ts:
        return ""
    d = datetime.fromtimestamp(ts)
    days = (datetime.now().date() - d.date()).days
    return {0: "today", 1: "yesterday"}.get(days) or (f"{days} days ago" if days < 7 else d.strftime("%d %b"))


def show_episodes(eps, heading):
    last({"episodes": eps})
    print(heading)
    for n, e in enumerate(eps, 1):
        extra = ", ".join(x for x in (when(e["at"]), e["length"]) if x)
        print(f"{n:>2}. {e['show']}: {e['title']}" + (f" ({extra})" if extra else ""))
    print("Say `podcasts play <number>` for the audio link.")


# --- commands -------------------------------------------------------------------------------------

def cmd_new():
    items = followed()
    if not items:
        print("You follow no podcasts yet. Say: podcasts search <words>, then podcasts follow <number>.")
        return
    week = time.time() - 7 * 86400
    fresh, broken = [], []
    for name, feed in items:
        eps = episodes(feed, name)
        if eps is None:
            broken.append(name)
            continue
        fresh += [e for e in eps if e["at"] >= week]
    fresh.sort(key=lambda e: e["at"], reverse=True)
    if fresh:
        show_episodes(fresh[:15], "New this week:")
    else:
        print("Nothing new this week.")
    if broken:
        print("Could not read: " + ", ".join(broken) + ".")


def cmd_search(args):
    words = " ".join(args).strip()
    if not words:
        sys.exit("podcasts search <words>")
    hits = search(words)
    if not hits:
        print(f"No podcasts for {words}.")
        return
    last({"shows": hits})
    print(f"Podcasts for {words}:")
    for n, h in enumerate(hits, 1):
        extra = ", ".join(x for x in (h["by"], h["genre"], f"{h['count']} episodes" if h["count"] else "") if x)
        print(f"{n:>2}. {h['name']}" + (f" ({extra})" if extra else ""))
    print("Say `podcasts follow <number>` to follow one.")


def cmd_follow(args):
    ref = " ".join(args).strip()
    if not ref:
        sys.exit("podcasts follow <number or name>")
    shows = last().get("shows") or []
    if ref.isdigit():
        if not 1 <= int(ref) <= len(shows):
            sys.exit("That number is not in the last search. Search first.")
        show = shows[int(ref) - 1]
    else:
        hits = search(ref, 3)
        if not hits:
            sys.exit(f"No podcast called {ref}.")
        show = hits[0]
    name = show["name"].replace("|", " ").replace(",", "")
    items = followed()
    if show["feed"] in [f for _, f in items]:
        print(f"You already follow {name}.")
        return
    eps = episodes(show["feed"], name)
    if eps is None:
        sys.exit(f"The feed of {name} could not be read.")
    store(items + [(name, show["feed"])])
    newest = f" The newest: {eps[0]['title']} ({when(eps[0]['at'])})." if eps else ""
    print(f"Following {name}.{newest}")


def cmd_unfollow(args):
    name = " ".join(args).strip().lower()
    items = followed()
    left = [x for x in items if x[0].lower() != name and name not in x[0].lower()]
    if len(left) == len(items):
        sys.exit(f"You do not follow {' '.join(args)}.")
    store(left)
    gone = [x[0] for x in items if x not in left]
    print(f"No longer following {', '.join(gone)}.")


def cmd_episodes(args):
    count = 5
    if args and args[-1].isdigit():
        count = max(1, min(int(args.pop()), 30))
    name = " ".join(args).strip().lower()
    match = [x for x in followed() if name and (x[0].lower() == name or name in x[0].lower())]
    if not match:
        sys.exit(f"You do not follow a podcast called {' '.join(args)}. `podcasts list` shows them.")
    show, feed = match[0]
    eps = episodes(feed, show)
    if not eps:
        sys.exit(f"The feed of {show} could not be read.")
    show_episodes(eps[:count], f"The latest of {show}:")


def cmd_play(args):
    if not args or not args[0].isdigit():
        sys.exit("podcasts play <number>")
    eps = last().get("episodes") or []
    n = int(args[0])
    if not 1 <= n <= len(eps):
        sys.exit("That number is not in the last list of episodes.")
    e = eps[n - 1]
    print(f"{e['show']}: {e['title']}" + (f" ({e['length']})" if e["length"] else ""))
    if e["about"]:
        print(e["about"])
    print(e["audio"] or "This episode has no audio link.")


def cmd_list():
    items = followed()
    if not items:
        print("You follow no podcasts yet.")
        return
    print(f"You follow {len(items)} podcast{'s' if len(items) != 1 else ''}: " + ", ".join(n for n, _ in items) + ".")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in ("shows", "country"):
        sys.exit("podcasts settings set <shows|country> <value>")
    value = " ".join(args[2:]).strip()
    if args[1] == "country":
        if not re.fullmatch(r"[A-Za-z]{2}", value):
            sys.exit("A country is two letters, like NL.")
        keep("country", value.upper())
        print(f"Searching the {value.upper()} directory.")
    else:
        keep("shows", value)
        print(f"Following {len(followed())} podcasts.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    commands = {"search": cmd_search, "follow": cmd_follow, "unfollow": cmd_unfollow, "episodes": cmd_episodes,
                "play": cmd_play, "list": lambda a: cmd_list()}
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_new()
    elif cmd in commands:
        commands[cmd](rest)
    elif cmd == "settings":
        cmd_settings(rest)
    else:
        cmd_search(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
