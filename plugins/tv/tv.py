#!/usr/bin/env python3
"""Television and series, from TVmaze: what is on tonight, and when the next episode of a show comes.

  tv                                    the shows you follow: episodes in the next two weeks
  tv tonight [country]                  prime time tonight (19:00 to 23:00), per channel
  tv show <name>                        one show: status, channel, the last and the next episode
  tv follow <name> / tv unfollow <name> keep a show, or stop
  tv settings                           the values as JSON
  tv settings set country <code>        the country for tonight (NL, BE, DE, GB, US...)

No key and no account. Times are the channel's own time for tonight, and local time for episodes.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
API = "https://api.tvmaze.com/"
DEFAULT = {"country": "NL", "shows": ""}
EMBED = [("embed[]", "nextepisode"), ("embed[]", "previousepisode")]


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


def get(path, params=(), missing_ok=False):
    url = API + path + ("?" + urllib.parse.urlencode(list(params)) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "Iris-tv/1.0"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and missing_ok:
                return None
            if exc.code == 429:
                sys.exit("TVmaze asks to slow down. Try again in a minute.")
            sys.exit(f"TVmaze answered with status {exc.code}.")
        except (OSError, ValueError):
            if attempt == 2:
                sys.exit("TVmaze did not answer. Try again in a minute.")


def channel(show):
    return ((show.get("network") or show.get("webChannel") or {}).get("name")) or ""


def when(ep):
    """An episode's moment, in local time."""
    stamp = ep.get("airstamp")
    if stamp:
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
        except ValueError:
            pass
    if ep.get("airdate"):
        return datetime.fromisoformat(ep["airdate"])
    return None


def ep_label(ep):
    code = f"S{ep.get('season', 0):02d}E{ep.get('number') or 0:02d}"
    name = ep.get("name") or ""
    return f"{code}" + (f" {name}" if name and not name.lower().startswith("episode") else "")


def day_label(d):
    days = (d.date() - date.today()).days
    base = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(days) or (
        d.strftime("%a %d %b") if d.year == date.today().year else d.strftime("%d %b %Y"))
    has_time = d.hour or d.minute
    return base + (d.strftime(" %H:%M") if has_time else "")


def said(text):
    """A sentence ending: no full stop after a name that already ends in ? or !."""
    return text if text[-1:] in "?!." else text + "."


def find_show(name):
    show = get("singlesearch/shows", [("q", name)] + EMBED, missing_ok=True)
    if not show:
        sys.exit(f"TVmaze knows no show called {name}.")
    return show


def followed():
    out = []
    for part in values()["shows"].split(","):
        name, _, sid = part.strip().rpartition("|")
        if sid.strip().isdigit():
            out.append((name.strip(), int(sid)))
    return out


def store(items):
    keep("shows", ", ".join(f"{n}|{i}" for n, i in items))


# --- commands -------------------------------------------------------------------------------------

def cmd_upcoming():
    items = followed()
    if not items:
        print("You follow no shows yet. Say: tv follow <name>.")
        return
    soon, later, ended = [], [], []
    for name, sid in items:
        show = get(f"shows/{sid}", EMBED, missing_ok=True)
        if not show:
            continue
        nxt = (show.get("_embedded") or {}).get("nextepisode")
        if nxt and when(nxt):
            d = when(nxt)
            (soon if (d.date() - date.today()).days <= 14 else later).append((d, show["name"], nxt, channel(show)))
        else:
            ended.append((show["name"], show.get("status", "")))
    if soon:
        print("Coming up:")
        for d, name, ep, ch in sorted(soon, key=lambda x: x[0].replace(tzinfo=None)):
            print(f"  {day_label(d)}  {name} {ep_label(ep)}" + (f" ({ch})" if ch else ""))
    else:
        print("Nothing new in the next two weeks.")
    for d, name, ep, _ in sorted(later, key=lambda x: x[0].replace(tzinfo=None)):
        print(f"Later: {name} {ep_label(ep)} on {d.strftime('%d %b %Y')}.")
    for name, status in ended:
        print(f"{name}: no next episode announced" + (" (the show has ended)" if status == "Ended" else "") + ".")


def cmd_tonight(args):
    country = (args[0] if args else values()["country"]).upper()
    rows = get("schedule", [("country", country), ("date", date.today().isoformat())])
    prime = [r for r in rows or [] if "19:00" <= (r.get("airtime") or "") < "23:00"]
    if not prime:
        print(f"No prime-time listings for {country} tonight.")
        return
    print(f"Tonight on TV ({country}):")
    for r in sorted(prime, key=lambda r: (r.get("airtime"), channel(r["show"]))):
        show = r["show"]
        ep = f" {ep_label(r)}" if r.get("season") else ""
        print(f"  {r['airtime']}  {channel(show) or '?':<12} {show['name']}{ep}")


def cmd_show(args):
    name = " ".join(args).strip()
    if not name:
        sys.exit("tv show <name>")
    show = find_show(name)
    embedded = show.get("_embedded") or {}
    status = {"Running": "still running", "Ended": "ended", "To Be Determined": "waiting for news",
              "In Development": "in development"}.get(show.get("status"), (show.get("status") or "").lower())
    years = (show.get("premiered") or "")[:4]
    print(f"{show['name']}" + (f" ({years})" if years else "") + (f", {channel(show)}" if channel(show) else "")
          + (f", {status}" if status else "") + ".")
    prev, nxt = embedded.get("previousepisode"), embedded.get("nextepisode")
    if prev and when(prev):
        print(f"Last episode: {ep_label(prev)}, {day_label(when(prev))}.")
    if nxt and when(nxt):
        print(f"Next episode: {ep_label(nxt)}, {day_label(when(nxt))}.")
    elif show.get("status") != "Ended":
        print("No next episode announced yet.")
    if show.get("id") in [i for _, i in followed()]:
        print("You follow it.")


def cmd_follow(args, on):
    name = " ".join(args).strip()
    if not name:
        sys.exit(f"tv {'follow' if on else 'unfollow'} <name>")
    items = followed()
    if not on:
        left = [x for x in items if x[0].lower() != name.lower()]
        if len(left) == len(items):
            show = find_show(name)
            left = [x for x in items if x[1] != show["id"]]
        if len(left) == len(items):
            sys.exit(f"You do not follow {name}.")
        store(left)
        print(f"No longer following {name}.")
        return
    show = find_show(name)
    if "|" in show["name"] or "," in show["name"]:
        clean = show["name"].replace("|", " ").replace(",", "")
    else:
        clean = show["name"]
    if show["id"] in [i for _, i in items]:
        print(said(f"You already follow {show['name']}"))
        return
    store(items + [(clean, show["id"])])
    nxt = (show.get("_embedded") or {}).get("nextepisode")
    print(said(f"Following {show['name']}") + (f" Next: {ep_label(nxt)}, {day_label(when(nxt))}." if nxt and when(nxt) else ""))


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) >= 2 and args[0] == "set" and args[1] == "shows":
        keep("shows", " ".join(args[2:]).strip())
        print(f"Following {len(followed())} shows.")
        return
    if len(args) < 3 or args[0] != "set" or args[1] != "country" or len(args[2]) != 2 or not args[2].isalpha():
        sys.exit("tv settings set country <two letters, like NL>, or tv settings set shows <Name|id, ...>")
    keep("country", args[2].upper())
    print(f"Tonight's listings are for {args[2].upper()}.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_upcoming()
    elif cmd == "tonight":
        cmd_tonight(rest)
    elif cmd == "show":
        cmd_show(rest)
    elif cmd == "follow":
        cmd_follow(rest, True)
    elif cmd == "unfollow":
        cmd_follow(rest, False)
    elif cmd == "settings":
        cmd_settings(rest)
    else:
        cmd_show(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
