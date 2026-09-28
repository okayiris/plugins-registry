#!/usr/bin/env python3
"""News and blogs you follow, from their RSS or Atom feeds. Nothing is sent, only read.

  feeds                                 the newest items of all feeds together
  feeds latest [name] [count]           the newest items, of one feed or all (10 by default)
  feeds search <text>                   items whose title or summary has the text
  feeds read <number>                   the summary and link of an item from the last list
  feeds list                            the feeds you follow
  feeds add "<name>" <link>             follow a feed
  feeds remove "<name>"                 stop following one (by name or link)
  feeds settings                        the values as JSON
  feeds settings set <key> <value>      change one value

A feed is a link to an RSS or Atom file, like https://feeds.nos.nl/nosnieuwsalgemeen. Most news sites
and blogs have one; a site's own address works too when its page points to its feed.
The list lives in values.json next to this file; the feeds are read again after 15 minutes.
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
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
CACHE_FILE = os.path.join(HERE, ".cache.json")
LAST_FILE = os.path.join(HERE, ".last.json")
CACHE_TTL = 15 * 60
DEFAULT = {"feeds": "", "count": "10"}
ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
DC_DATE = "{http://purl.org/dc/elements/1.1/}date"


# --- values ---------------------------------------------------------------------------------------

def load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(fallback)) else fallback
    except (OSError, ValueError):
        return fallback


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def values():
    out = dict(DEFAULT)
    out.update({str(k): str(v) for k, v in load_json(VALUES_FILE, {}).items()})
    return out


def keep(key, value):
    data = load_json(VALUES_FILE, {})
    data[key] = value
    save_json(VALUES_FILE, data)


def feed_list():
    """The feeds as (name, link), from the comma separated list `Name|link, Name|link`."""
    out = []
    for part in values()["feeds"].split(","):
        part = part.strip()
        if not part:
            continue
        name, _, link = part.rpartition("|")
        if not link.startswith("http"):
            continue
        out.append((name.strip() or urllib.parse.urlparse(link).netloc, link.strip()))
    return out


def store_feeds(feeds):
    keep("feeds", ", ".join(f"{name}|{link}" for name, link in feeds))


# --- reading --------------------------------------------------------------------------------------

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value, limit=None):
    if not value:
        return ""
    parser = Text()
    parser.feed(html.unescape(value) if "&lt;" in value else value)
    text = re.sub(r"\s+", " ", html.unescape("".join(parser.parts))).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."
    return text


def when(value):
    if not value:
        return None
    value = value.strip()
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def fetch(link):
    req = urllib.request.Request(link, headers={"User-Agent": "Iris-feeds/1.0",
                                                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read(4_000_000), resp.headers.get_content_type()


def discover(link, body):
    """A site's own page often names its feed in a <link rel="alternate">."""
    page = body.decode("utf-8", "replace")
    for tag in re.findall(r"<link[^>]+>", page, re.I):
        if re.search(r"application/(rss|atom)\+xml", tag, re.I):
            m = re.search(r'href=["\']([^"\']+)', tag, re.I)
            if m:
                return urllib.parse.urljoin(link, html.unescape(m.group(1)))
    return None


def parse(body, source):
    root = ET.fromstring(body)
    items = []
    if root.tag == ATOM + "feed":
        for e in root.findall(ATOM + "entry"):
            link = ""
            for l in e.findall(ATOM + "link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            items.append({
                "title": plain(e.findtext(ATOM + "title")),
                "link": link,
                "summary": plain(e.findtext(ATOM + "summary") or e.findtext(ATOM + "content"), 600),
                "at": when(e.findtext(ATOM + "updated") or e.findtext(ATOM + "published")),
                "feed": source,
            })
    else:
        for e in root.iter("item"):
            items.append({
                "title": plain(e.findtext("title")),
                "link": (e.findtext("link") or e.findtext("guid") or "").strip(),
                "summary": plain(e.findtext("description") or e.findtext(CONTENT), 600),
                "at": when(e.findtext("pubDate") or e.findtext(DC_DATE)),
                "feed": source,
            })
    return [i for i in items if i["title"]]


def read_feed(name, link):
    body, _ = fetch(link)
    try:
        return parse(body, name)
    except ET.ParseError:
        found = discover(link, body)
        if not found:
            raise ValueError("this link is not a feed")
        body, _ = fetch(found)
        return parse(body, name)


def all_items(only=None, fresh=False):
    cache = load_json(CACHE_FILE, {})
    now = time.time()
    items, problems, changed = [], [], False
    for name, link in feed_list():
        if only and only.lower() not in (name.lower(), link.lower()):
            continue
        hit = cache.get(link)
        if hit and not fresh and now - hit.get("read", 0) < CACHE_TTL:
            items += hit["items"]
            continue
        try:
            got = read_feed(name, link)
            cache[link] = {"read": now, "items": got}
            changed = True
            items += got
        except (OSError, ValueError, ET.ParseError, urllib.error.URLError):
            problems.append(name)
            if hit:
                items += hit["items"]
    if changed:
        known = {link for _, link in feed_list()}
        save_json(CACHE_FILE, {k: v for k, v in cache.items() if k in known})
    items.sort(key=lambda i: i.get("at") or 0, reverse=True)
    return items, problems


def age(ts):
    if not ts:
        return ""
    minutes = int((time.time() - ts) / 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return datetime.fromtimestamp(ts).strftime("%d %b")


def show(items, problems, heading):
    if not items:
        print("Nothing to read." if not problems else f"Could not read: {', '.join(problems)}.")
        return
    print(heading)
    for n, i in enumerate(items, 1):
        stamp = age(i.get("at"))
        print(f"{n:>2}. {i['title']}  ({i['feed']}{', ' + stamp if stamp else ''})")
    save_json(LAST_FILE, items)
    if problems:
        print(f"Could not read: {', '.join(problems)}.")
    print("Say `feeds read <number>` for the summary and the link.")


# --- commands -------------------------------------------------------------------------------------

def need_feeds():
    if not feed_list():
        sys.exit('No feeds yet. Follow one with: feeds add "<name>" <link>.')


def cmd_latest(args):
    need_feeds()
    count = int(values()["count"] or 10)
    only = None
    for a in args:
        if a.isdigit():
            count = int(a)
        else:
            only = a if only is None else f"{only} {a}"
    if only and not any(only.lower() in (n.lower(), l.lower()) for n, l in feed_list()):
        sys.exit(f"You do not follow a feed called {only}. `feeds list` shows them.")
    items, problems = all_items(only)
    show(items[:max(1, min(count, 50))], problems, f"The newest from {only}:" if only else "The newest:")


def cmd_search(args):
    need_feeds()
    if not args:
        sys.exit("feeds search <text>")
    needle = " ".join(args).lower()
    items, problems = all_items()
    hits = [i for i in items if needle in i["title"].lower() or needle in i["summary"].lower()]
    if not hits:
        print(f"Nothing about {needle} in your feeds right now.")
        return
    show(hits[:20], problems, f"About {needle}:")


def cmd_read(args):
    if not args or not args[0].isdigit():
        sys.exit("feeds read <number>")
    last = load_json(LAST_FILE, [])
    n = int(args[0])
    if not 1 <= n <= len(last):
        sys.exit("That number is not in the last list. Ask for the newest first.")
    i = last[n - 1]
    print(f"{i['title']} ({i['feed']})")
    if i.get("summary"):
        print(i["summary"])
    if i.get("link"):
        print(i["link"])


def cmd_list():
    feeds = feed_list()
    if not feeds:
        print('No feeds yet. Follow one with: feeds add "<name>" <link>.')
        return
    print(f"You follow {len(feeds)} feed{'s' if len(feeds) != 1 else ''}:")
    for name, link in feeds:
        print(f"  {name}  {link}")


def cmd_add(args):
    if len(args) < 2 and not (args and args[0].startswith("http")):
        sys.exit('feeds add "<name>" <link>')
    link = args[-1]
    name = " ".join(args[:-1]).strip() or urllib.parse.urlparse(link).netloc
    if not re.match(r"^https?://", link):
        sys.exit("A feed link starts with http:// or https://.")
    if "|" in name or "," in name:
        sys.exit("A feed name cannot hold | or a comma.")
    try:
        body, _ = fetch(link)
        try:
            items = parse(body, name)
        except ET.ParseError:
            found = discover(link, body)
            if not found:
                sys.exit("That link is not a feed, and the page does not point to one.")
            link = found
            body, _ = fetch(link)
            items = parse(body, name)
    except (OSError, urllib.error.URLError, ET.ParseError):
        sys.exit("That link could not be read as a feed.")
    feeds = [(n, l) for n, l in feed_list() if l != link and n.lower() != name.lower()]
    store_feeds(feeds + [(name, link)])
    newest = f" The newest: {items[0]['title']}." if items else ""
    print(f"Following {name}, {len(items)} items.{newest}")


def cmd_remove(args):
    if not args:
        sys.exit('feeds remove "<name>"')
    what = " ".join(args).lower()
    feeds = feed_list()
    gone = [n for n, l in feeds if what in (n.lower(), l.lower())]
    if not gone:
        sys.exit(f"You do not follow a feed called {' '.join(args)}.")
    store_feeds([(n, l) for n, l in feeds if what not in (n.lower(), l.lower())])
    print(f"No longer following {gone[0]}.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set":
        sys.exit("feeds settings set <feeds|count> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "count":
        if not value.isdigit() or not 1 <= int(value) <= 50:
            sys.exit("The count is a number from 1 to 50.")
        keep("count", value)
        print(f"Showing {value} items at a time.")
    elif key == "feeds":
        keep("feeds", value)
        print(f"{len(feed_list())} feeds.")
    else:
        sys.exit(f"There is no setting called {key}. Use feeds or count.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("latest", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "latest":
        cmd_latest(rest)
    elif cmd == "search":
        cmd_search(rest)
    elif cmd == "read":
        cmd_read(rest)
    elif cmd == "list":
        cmd_list()
    elif cmd == "add":
        cmd_add(rest)
    elif cmd == "remove":
        cmd_remove(rest)
    elif cmd == "refresh":
        need_feeds()
        items, problems = all_items(fresh=True)
        show(items[:int(values()["count"] or 10)], problems, "The newest:")
    elif cmd == "settings":
        cmd_settings(rest)
    else:
        cmd_latest(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
