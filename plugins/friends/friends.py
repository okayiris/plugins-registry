#!/usr/bin/env python3
"""Your own wall, friends and followers, between Iris houses: post text and photos, add friends, follow
walls, and like and comment on what your friends post. No central service: every house keeps its own
wall at https://<house>.okayiris.com/wall, and houses talk to each other's wall directly.

For the owner:
  friends                                what is new: requests, likes, comments, followers
  friends post "<text>" [photo <file or https link>] [public|friends]
  friends wall                           your own posts, with likes and comments
  friends delete <n>                     take a post off your wall
  friends feed                           the newest posts of your friends and the walls you follow
  friends add <house>                    ask a house to be friends (anna, or anna.okayiris.com)
  friends accept <house> / friends decline <house>
  friends remove <house>                 no longer friends (or take back a request)
  friends requests                       open requests, both ways
  friends list                           friends, following and followers
  friends follow <house> / friends unfollow <house>
  friends profile <house>                someone's wall: who, and their latest posts
  friends like <house>/<n> / friends unlike <house>/<n>
  friends comment <house>/<n> "<text>"   (me/<n> for your own post)
  friends block <house> / friends unblock <house>
  friends news                           everything that happened lately
  friends avatar <file or https link>    your profile photo (none: no photo)
  friends link                           the address of your wall
  friends settings / friends settings set <key> <value>

For the window: `friends data --json`, `friends feed --json`, `friends photo <house|me> <n|avatar> --json`.

For the wall (the route /wall): the house runs this command with the request as JSON on stdin, and
what it prints is the answer. Other houses call it too: profile, posts, photo, request, check, accept,
unfriend, follow, following, like and comment.

Friends-only posts are shown to a house only with the key this house gave it when they became
friends. Every request, accept and follow is checked with the house it claims to come from, by calling
that house's own address back, so nobody can pretend to be someone else's house.
"""
import base64
import json
import os
import re
import secrets
import select
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
ROUTE = "wall"
DOMAIN = "okayiris.com"
DEFAULT = {"house": "", "name": "", "bio": "", "audience": "friends", "requests": "on"}
HOUSE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
MAX_PHOTO = 4 * 1024 * 1024
MAX_ANSWER = 8 * 1024 * 1024
MAX_TEXT, MAX_COMMENT, MAX_PENDING = 2000, 500, 100
KINDS = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"GIF8": "image/gif"}


# --- values and database --------------------------------------------------------------------------

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


def db():
    con = sqlite3.connect(DB_FILE, timeout=10)
    con.row_factory = sqlite3.Row
    if not con.execute("select 1 from sqlite_master where type='table' and name='posts'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def now():
    return int(time.time())


def clean(value, limit):
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()[:limit]


def one_line(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def house_of(text):
    """anna, anna.okayiris.com or https://anna.okayiris.com/wall: the house, or None."""
    t = str(text or "").strip().lower()
    if "://" in t:
        t = urllib.parse.urlparse(t).hostname or ""
    t = t.split("/")[0]
    if t.endswith("." + DOMAIN):
        t = t[: -len(DOMAIN) - 1]
    return t if HOUSE.match(t) else None


def me(required=True):
    h = house_of(os.environ.get("IRIS_HOUSE", "")) or house_of(values()["house"])
    if not h and required:
        sys.exit("I do not know this house's name yet. Say it once with: friends settings set house <name> "
                 "(the first part of the house's address, like anna for anna.okayiris.com).")
    return h


def my_name():
    v = values()
    return v["name"] or (me(False) or "").capitalize()


def wall_url(house):
    return f"https://{house}.{DOMAIN}/{ROUTE}"


def ago(at):
    s = max(0, now() - int(at))
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    if s < 2 * 86400:
        return "yesterday"
    if s < 7 * 86400:
        return f"{s // 86400} days ago"
    return datetime.fromtimestamp(at).strftime("%-d %b %Y" if s > 300 * 86400 else "%-d %b")


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def news(con, kind, house, name="", post_id=None, text=""):
    con.execute("insert into news (kind, house, name, post_id, text, at) values (?, ?, ?, ?, ?, ?)",
                (kind, house, name, post_id, text, now()))
    con.execute("delete from news where id not in (select id from news order by id desc limit 200)")


# --- photos ---------------------------------------------------------------------------------------

def kind_of(raw):
    for magic, kind in KINDS.items():
        if raw.startswith(magic):
            return kind
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def shrink(raw, kind):
    """A big photo becomes at most 1600 pixels wide and high, when Pillow is there to do it."""
    if len(raw) <= 1_500_000 or kind == "image/gif":
        return raw, kind
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((1600, 1600))
        out = io.BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=85)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return raw, kind


def read_photo(where):
    """(type, bytes) of a photo from a file in the house or an https link; exits with a reason."""
    where = str(where).strip()
    if where.startswith("https://"):
        try:
            req = urllib.request.Request(where, headers={"User-Agent": "iris-friends/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read(MAX_PHOTO + 1)
        except (urllib.error.URLError, OSError, ValueError):
            sys.exit(f"The photo at {where} could not be fetched.")
    elif where.startswith("http://"):
        sys.exit("A photo link starts with https://.")
    else:
        path = os.path.expanduser(where)
        if not os.path.isfile(path):
            sys.exit(f"There is no file {where}.")
        with open(path, "rb") as f:
            raw = f.read(MAX_PHOTO * 4 + 1)
    kind = kind_of(raw)
    if not kind:
        sys.exit("That is not a photo this wall can show: use a JPEG, PNG, GIF or WebP.")
    raw, kind = shrink(raw, kind)
    if len(raw) > MAX_PHOTO:
        sys.exit(f"The photo is {len(raw) / 1024 / 1024:.1f} MB; make it smaller than 4 MB first.")
    return kind, raw


def keep_photo(con, kind, raw):
    return con.execute("insert into photos (type, data, at) values (?, ?, ?)", (kind, raw, now())).lastrowid


# --- talking to other houses ----------------------------------------------------------------------

def call(house, payload, timeout=8):
    """(answer, problem): one request to another house's wall. problem is '' when it answered."""
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    req = urllib.request.Request(wall_url(house) + "/api", data=data, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "iris-friends/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(MAX_ANSWER)
    except urllib.error.HTTPError as exc:
        return None, "no wall" if exc.code == 404 else f"status {exc.code}"
    except (urllib.error.URLError, OSError, ValueError):
        return None, "unreachable"
    try:
        answer = json.loads(raw)
    except ValueError:
        return None, "no wall"
    return (answer, "") if isinstance(answer, dict) else (None, "no wall")


def why(house, problem):
    if problem == "no wall":
        return f"{house}.{DOMAIN} has no wall: they need the friends plugin, switched on."
    return f"{house}.{DOMAIN} could not be reached ({problem}). Try again later."


# --- the wall, for visitors and other houses (route) ----------------------------------------------

def friend_of(con, house, key):
    """The friend row of a house that shows the key this house gave it; None for anyone else."""
    if not house or not key:
        return None
    row = con.execute("select * from friends where house = ? and state = 'friends'", (house,)).fetchone()
    if row and row["my_key"] and secrets.compare_digest(row["my_key"], str(key)):
        return row
    return None


def visible(fr):
    return ("public", "friends") if fr else ("public",)


def post_json(con, p, fr):
    likes = con.execute("select house, name from likes where post_id = ? order by at", (p["id"],)).fetchall()
    count = con.execute("select count(*) from comments where post_id = ?", (p["id"],)).fetchone()[0]
    out = {"id": p["id"], "text": p["text"], "audience": p["audience"], "photo": bool(p["photo"]), "at": p["at"],
           "likes": len(likes), "comments": count}
    if fr:  # who liked and what was said: for friends only, never on the open wall
        out["liked"] = any(l["house"] == fr["house"] for l in likes)
        out["thread"] = [{"house": c["house"], "name": c["name"], "text": c["text"], "at": c["at"]}
                         for c in reversed(con.execute("select * from comments where post_id = ? order by id desc limit 20",
                                                       (p["id"],)).fetchall())]
    return out


def api_profile(args):
    v = values()
    with db() as con:
        fr = friend_of(con, house_of(args.get("from")), args.get("key"))
        aud = visible(fr)
        posts = con.execute(f"select count(*) from posts where audience in ({','.join('?' * len(aud))})", aud).fetchone()[0]
        friends = con.execute("select count(*) from friends where state = 'friends'").fetchone()[0]
        followers = con.execute("select count(*) from followers").fetchone()[0]
        following = con.execute("select count(*) from follows").fetchone()[0]
    return {"house": me(False) or "", "name": my_name(), "bio": v["bio"], "avatar": bool(v.get("avatar")),
            "posts": posts, "friends": friends, "followers": followers, "following": following,
            "requests": v["requests"] == "on", "friend": bool(fr)}


def api_posts(args):
    try:
        before = int(args.get("before") or 0) or 2 ** 62
        limit = max(1, min(int(args.get("limit") or 20), 50))
    except (TypeError, ValueError):
        return {"error": "bad request"}
    with db() as con:
        fr = friend_of(con, house_of(args.get("from")), args.get("key"))
        aud = visible(fr)
        rows = con.execute(f"select * from posts where audience in ({','.join('?' * len(aud))}) and id < ? "
                           "order by id desc limit ?", (*aud, before, limit)).fetchall()
        posts = [post_json(con, p, fr) for p in rows]
    return {"house": me(False) or "", "name": my_name(), "friend": bool(fr), "posts": posts, "more": len(rows) == limit}


def api_photo(args, owner=False):
    v = values()
    with db() as con:
        fr = friend_of(con, house_of(args.get("from")), args.get("key")) or owner
        if str(args.get("id")) == "avatar":
            pid = int(v["avatar"]) if str(v.get("avatar", "")).isdigit() else None
        else:
            try:
                post = con.execute("select * from posts where id = ?", (int(args.get("id")),)).fetchone()
            except (TypeError, ValueError):
                post = None
            pid = post["photo"] if post and post["audience"] in visible(fr) else None
        row = con.execute("select * from photos where id = ?", (pid,)).fetchone() if pid else None
    if not row:
        return {"error": "unknown"}
    return {"type": row["type"], "data": base64.b64encode(row["data"]).decode()}


def sender(args):
    who = house_of(args.get("from"))
    return who if who and who != me(False) else None


def api_request(args):
    """Someone asks to be friends. Checked with their own house before the owner ever sees it."""
    who, key, name = sender(args), str(args.get("key") or ""), one_line(args.get("name"), 60)
    if not who or not 16 <= len(key) <= 100:
        return {"error": "bad request"}
    with db() as con:
        row = con.execute("select * from friends where house = ?", (who,)).fetchone()
        asked = con.execute("select count(*) from friends where state = 'asked'").fetchone()[0]
    if row and row["state"] == "blocked":
        return {"ok": True}                      # a blocked house hears nothing different
    if values()["requests"] != "on" and not row:
        return {"error": "closed"}
    if not row and asked >= MAX_PENDING:
        return {"error": "full"}
    answer, _ = call(who, {"action": "check", "to": me(False), "key": key}, timeout=6)
    if not answer or answer.get("ok") is not True:
        return {"error": "unverified"}
    with db() as con:
        row = con.execute("select * from friends where house = ?", (who,)).fetchone()
        if row and row["state"] in ("sent", "friends"):
            # We asked each other, or they lost their side: friends, with the key I gave them before.
            con.execute("update friends set state = 'friends', their_key = ?, name = ?, at = ? where house = ?",
                        (key, name or row["name"], now(), who))
            if row["state"] == "sent":
                news(con, "friends", who, name)
            return {"ok": True, "friends": True, "key": row["my_key"], "name": my_name()}
        con.execute("insert into friends (house, name, state, their_key, at) values (?, ?, 'asked', ?, ?) "
                    "on conflict (house) do update set name = excluded.name, their_key = excluded.their_key, at = excluded.at",
                    (who, name, key, now()))
        con.execute("delete from news where kind = 'request' and house = ?", (who,))
        news(con, "request", who, name)
    return {"ok": True}


def api_check(args):
    """Did this house really ask that house? Only this house and the one it asked know the key."""
    to, key = house_of(args.get("to")), str(args.get("key") or "")
    with db() as con:
        row = con.execute("select * from friends where house = ? and state in ('sent', 'friends')", (to,)).fetchone()
    return {"ok": bool(row and row["my_key"] and key and secrets.compare_digest(row["my_key"], key))}


def api_accept(args):
    who, key, theirs = sender(args), str(args.get("key") or ""), str(args.get("their") or "")
    if not who or not 16 <= len(theirs) <= 100:
        return {"error": "bad request"}
    with db() as con:
        row = con.execute("select * from friends where house = ? and state = 'sent'", (who,)).fetchone()
        if not row or not secrets.compare_digest(row["my_key"] or "", key):
            return {"error": "unknown"}
        name = one_line(args.get("name"), 60) or row["name"]
        con.execute("update friends set state = 'friends', their_key = ?, name = ?, at = ? where house = ?",
                    (theirs, name, now(), who))
        news(con, "friends", who, name)
    return {"ok": True, "name": my_name()}


def api_unfriend(args):
    """No longer friends, a request taken back or declined: either of the two keys proves who it is."""
    who, key = sender(args), str(args.get("key") or "")
    if who and key:
        with db() as con:
            row = con.execute("select * from friends where house = ? and state != 'blocked'", (who,)).fetchone()
            if row and any(k and secrets.compare_digest(k, key) for k in (row["my_key"], row["their_key"])):
                con.execute("delete from friends where house = ?", (who,))
                con.execute("delete from news where kind = 'request' and house = ?", (who,))
                forget_feed(con, who)
    return {"ok": True}


def api_follow(args):
    """A house says it follows this wall, or stopped: ask that house itself, and keep its answer."""
    who = sender(args)
    if not who:
        return {"error": "bad request"}
    with db() as con:
        blocked = con.execute("select 1 from friends where house = ? and state = 'blocked'", (who,)).fetchone()
    if blocked:
        return {"ok": True}
    answer, _ = call(who, {"action": "following", "to": me(False)}, timeout=6)
    follows = bool(answer and answer.get("ok") is True)
    with db() as con:
        was = con.execute("select 1 from followers where house = ?", (who,)).fetchone()
        if follows:
            con.execute("insert into followers (house, name, at) values (?, ?, ?) on conflict (house) do update set name = excluded.name",
                        (who, one_line(args.get("name"), 60), now()))
            if not was:
                news(con, "follower", who, one_line(args.get("name"), 60))
        else:
            con.execute("delete from followers where house = ?", (who,))
    return {"ok": True, "following": follows}


def api_following(args):
    to = house_of(args.get("to"))
    with db() as con:
        return {"ok": bool(to and con.execute("select 1 from follows where house = ?", (to,)).fetchone())}


def own_post(con, args):
    try:
        return con.execute("select * from posts where id = ?", (int(args.get("post")),)).fetchone()
    except (TypeError, ValueError):
        return None


def api_like(args):
    with db() as con:
        fr = friend_of(con, sender(args), args.get("key"))
        post = own_post(con, args)
        if not fr or not post:
            return {"error": "unknown"}
        if args.get("on", True) is False:
            con.execute("delete from likes where post_id = ? and house = ?", (post["id"], fr["house"]))
        elif not con.execute("select 1 from likes where post_id = ? and house = ?", (post["id"], fr["house"])).fetchone():
            con.execute("insert into likes (post_id, house, name, at) values (?, ?, ?, ?)",
                        (post["id"], fr["house"], fr["name"], now()))
            news(con, "like", fr["house"], fr["name"], post["id"])
        return {"ok": True, "likes": con.execute("select count(*) from likes where post_id = ?", (post["id"],)).fetchone()[0]}


def api_comment(args):
    text = clean(args.get("text"), MAX_COMMENT)
    with db() as con:
        fr = friend_of(con, sender(args), args.get("key"))
        post = own_post(con, args)
        if not fr or not post:
            return {"error": "unknown"}
        if not text:
            return {"error": "empty"}
        if con.execute("select count(*) from comments where post_id = ?", (post["id"],)).fetchone()[0] >= 500:
            return {"error": "full"}
        con.execute("insert into comments (post_id, house, name, text, at) values (?, ?, ?, ?, ?)",
                    (post["id"], fr["house"], fr["name"], text, now()))
        news(con, "comment", fr["house"], fr["name"], post["id"], text)
        return {"ok": True, "comments": con.execute("select count(*) from comments where post_id = ?", (post["id"],)).fetchone()[0]}


def api(request):
    body = request.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = {}
    body = body if isinstance(body, dict) else {}
    query = request.get("query") if isinstance(request.get("query"), dict) else {}
    args = body or query
    house = house_of(request.get("house"))
    if house and house != values()["house"] and not house_of(os.environ.get("IRIS_HOUSE", "")):
        keep("house", house)                     # the house learns its own name from its own address
    action = str(args.get("action") or "profile")
    reading = {"profile": api_profile, "posts": api_posts, "photo": api_photo, "check": api_check,
               "following": api_following}
    writing = {"request": api_request, "accept": api_accept, "unfriend": api_unfriend, "follow": api_follow,
               "like": api_like, "comment": api_comment}
    if action in reading:
        return reading[action](args)
    if action in writing:
        if request.get("method", "POST") != "POST":
            return {"error": "use POST"}
        return writing[action](args)
    return {"error": "unknown action"}


# --- the feed -------------------------------------------------------------------------------------

def sources(con):
    """Every house whose posts come into the feed, with the key to show it (friends) or None."""
    out = {r["house"]: None for r in con.execute("select house from follows")}
    for r in con.execute("select house, their_key from friends where state = 'friends'"):
        out[r["house"]] = r["their_key"]
    return out


def forget_feed(con, house):
    if house in sources(con):
        return
    con.execute("delete from feed where house = ?", (house,))
    con.execute("delete from feed_photos where house = ?", (house,))


def refresh_feed():
    """Ask every friend and followed house for its newest posts. Returns the houses that did not answer."""
    mine = me()
    with db() as con:
        wanted = sources(con)
    if not wanted:
        return []

    def ask(item):
        house, key = item
        payload = {"action": "posts", "from": mine, "limit": 20}
        if key:
            payload["key"] = key
        return house, call(house, payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(ask, wanted.items()))
    missed = []
    with db() as con:
        for house, (answer, problem) in answers:
            posts = (answer or {}).get("posts")
            if not isinstance(posts, list):
                missed.append((house, problem or "no wall"))
                continue
            name = one_line(answer.get("name"), 60) or house.capitalize()
            con.execute("update friends set name = ? where house = ?", (name, house))
            con.execute("update follows set name = ? where house = ?", (name, house))
            ids = []
            for p in posts[:50]:
                if not isinstance(p, dict) or not isinstance(p.get("id"), int):
                    continue
                ids.append(p["id"])
                thread = p.get("thread") if isinstance(p.get("thread"), list) else []
                thread = [{"house": house_of(c.get("house")) or "", "name": one_line(c.get("name"), 60),
                           "text": clean(c.get("text"), MAX_COMMENT), "at": int(c.get("at") or 0)}
                          for c in thread[-20:] if isinstance(c, dict)]
                con.execute(
                    "insert or replace into feed (house, post_id, name, text, audience, photo, at, likes, comments, liked, thread) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (house, p["id"], name, clean(p.get("text"), MAX_TEXT),
                     "friends" if p.get("audience") == "friends" else "public", 1 if p.get("photo") else 0,
                     int(p.get("at") or 0), int(p.get("likes") or 0), int(p.get("comments") or 0),
                     1 if p.get("liked") else 0, json.dumps(thread, ensure_ascii=False)))
            # What is gone there (deleted, or no longer shown to me) goes here too.
            if ids:
                con.execute(f"delete from feed where house = ? and post_id >= ? and post_id not in ({','.join('?' * len(ids))})",
                            (house, min(ids), *ids))
            else:
                con.execute("delete from feed where house = ?", (house,))
        con.execute("delete from feed where rowid not in (select rowid from feed order by at desc limit 300)")
        con.execute("delete from feed_photos where post_id != 'avatar' and not exists "
                    "(select 1 from feed where feed.house = feed_photos.house and cast(feed.post_id as text) = feed_photos.post_id)")
    return missed


def feed_rows(con, limit=40):
    return con.execute("select * from feed order by at desc, post_id desc limit ?", (limit,)).fetchall()


def feed_json(r, friends):
    return {"house": r["house"], "id": r["post_id"], "friend": r["house"] in friends, "name": r["name"], "text": r["text"], "audience": r["audience"],
            "photo": bool(r["photo"]), "at": r["at"], "likes": r["likes"], "comments": r["comments"],
            "liked": bool(r["liked"]), "thread": json.loads(r["thread"] or "[]")}


# --- the owner ------------------------------------------------------------------------------------

def ref(text):
    """anna/12, or anna 12: (house, post number)."""
    m = re.fullmatch(r"\s*([^/\s]+)\s*[/ #]\s*#?(\d+)\s*", str(text))
    if not m:
        return None, None
    house = "me" if m.group(1).lower() in ("me", "mine", "my") else house_of(m.group(1))
    return house, int(m.group(2))


def need_house(args, usage):
    me()                                         # the house knows its own name before it talks to another
    if not args:
        sys.exit(usage)
    h = house_of(args[0])
    if not h:
        sys.exit(f"{args[0]} is not a house. Give the first part of its address, like anna for anna.okayiris.com.")
    if h == me(False):
        sys.exit("That is this house itself.")
    return h


def label(house, name):
    if not name:
        return house
    return name if name.lower() == house else f"{name} ({house})"


def cmd_overview():
    mine = me(False)
    with db() as con:
        fresh = con.execute("select * from news where seen = 0 order by id desc limit 12").fetchall()
        friends = con.execute("select count(*) from friends where state = 'friends'").fetchone()[0]
        asked = con.execute("select * from friends where state = 'asked' order by at").fetchall()
        posts = con.execute("select count(*) from posts").fetchone()[0]
        followers = con.execute("select count(*) from followers").fetchone()[0]
        following = con.execute("select count(*) from follows").fetchone()[0]
    print(f"{my_name() or 'Your wall'}: {plural(posts, 'post')}, {plural(friends, 'friend')}, "
          f"{plural(followers, 'follower')}, following {following}.")
    if asked:
        print("Wants to be friends: " + ", ".join(label(r["house"], r["name"]) for r in asked)
              + ". Say friends accept <house> or friends decline <house>.")
    shown = [n for n in fresh if n["kind"] != "request"]
    if shown:
        print("New:")
        for n in shown:
            print("  " + news_line(n))
    elif not asked:
        print("Nothing new.")
    if not mine:
        print("This house does not know its own name yet: friends settings set house <name>.")
    elif not posts and not friends:
        print(f"Your wall is at {wall_url(mine)}. Post something with friends post \"...\", "
              "and add a friend with friends add <their house>.")


def news_line(n):
    who = label(n["house"], n["name"])
    return {
        "request": f"{who} wants to be friends ({ago(n['at'])})",
        "friends": f"{who} and you are friends now ({ago(n['at'])})",
        "like": f"{who} likes your post #{n['post_id']} ({ago(n['at'])})",
        "comment": f"{who} on your post #{n['post_id']}: \"{n['text']}\" ({ago(n['at'])})",
        "follower": f"{who} follows your wall ({ago(n['at'])})",
    }.get(n["kind"], f"{who}: {n['kind']}")


def cmd_news():
    with db() as con:
        rows = con.execute("select * from news order by id desc limit 20").fetchall()
        con.execute("update news set seen = 1 where seen = 0")
    if not rows:
        print("Nothing has happened on your wall yet.")
        return
    for n in rows:
        print(("* " if not n["seen"] else "  ") + news_line(n))


def cmd_post(args):
    text, photo, audience = [], None, values()["audience"]
    i = 0
    while i < len(args):
        a = args[i]
        if a.lower() == "photo" and i + 1 < len(args):
            photo = args[i + 1]
            i += 2
            continue
        if a.lower() in ("public", "everyone"):
            audience = "public"
        elif a.lower() in ("friends", "private"):
            audience = "friends"
        else:
            text.append(a)
        i += 1
    body = clean(" ".join(text).replace("\\n", "\n"), MAX_TEXT)
    if not body and not photo:
        sys.exit('friends post "<text>" [photo <file or https link>] [public|friends]')
    kind_raw = read_photo(photo) if photo else None
    with db() as con:
        pid = keep_photo(con, *kind_raw) if kind_raw else None
        cur = con.execute("insert into posts (text, photo, audience, at) values (?, ?, ?, ?)",
                          (body, pid, "public" if audience == "public" else "friends", now()))
    who = "everyone who opens your wall and your followers" if audience == "public" else "your friends"
    print(f"Posted #{cur.lastrowid}{' with a photo' if pid else ''}, for {who}.")


def post_lines(con, p, indent="  "):
    likes = con.execute("select house, name from likes where post_id = ? order by at", (p["id"],)).fetchall()
    comments = con.execute("select * from comments where post_id = ? order by id", (p["id"],)).fetchall()
    head = f"#{p['id']}  {ago(p['at'])}, {'public' if p['audience'] == 'public' else 'friends only'}"
    body = f"{head}: {one_line(p['text'], 200) or '(no text)'}" + (" [photo]" if p["photo"] else "")
    lines = [body]
    if likes:
        lines.append(indent + "liked by " + ", ".join(l["name"] or l["house"] for l in likes))
    for c in comments[-5:]:
        lines.append(f"{indent}{c['name'] or c['house']}: {one_line(c['text'], 200)}")
    if len(comments) > 5:
        lines.append(f"{indent}and {plural(len(comments) - 5, 'earlier comment')}")
    return lines


def cmd_wall():
    with db() as con:
        rows = con.execute("select * from posts order by id desc limit 15").fetchall()
        if not rows:
            print('Your wall is empty. Post something with: friends post "<text>" [photo <file>].')
            return
        for p in rows:
            lines = post_lines(con, p)
            print(lines[0])
            for l in lines[1:]:
                print("    " + l.strip())


def cmd_delete(args):
    if not args or not args[0].lstrip("#").isdigit():
        sys.exit("friends delete <n>")
    with db() as con:
        p = con.execute("select * from posts where id = ?", (int(args[0].lstrip("#")),)).fetchone()
        if not p:
            sys.exit(f"There is no post #{args[0].lstrip('#')} on your wall.")
        con.execute("delete from posts where id = ?", (p["id"],))
        con.execute("delete from likes where post_id = ?", (p["id"],))
        con.execute("delete from comments where post_id = ?", (p["id"],))
        if p["photo"]:
            con.execute("delete from photos where id = ?", (p["photo"],))
    print(f"Post #{p['id']} is off your wall; friends no longer see it once their feed refreshes.")


def cmd_feed(as_json=False):
    missed = refresh_feed()
    with db() as con:
        rows = feed_rows(con)
        empty = not sources(con)
        friends = {h for h, k in sources(con).items() if k}
    if as_json:
        print(json.dumps({"feed": [feed_json(r, friends) for r in rows], "missed": [h for h, _ in missed]}, ensure_ascii=False))
        return
    if empty:
        print("Your feed is empty: add a friend (friends add <house>) or follow a wall (friends follow <house>).")
        return
    if not rows:
        print("Nobody you follow has posted yet.")
    for r in rows[:15]:
        who = r["name"] or r["house"]
        extra = [plural(r["likes"], "like")] if r["likes"] else []
        if r["comments"]:
            extra.append(plural(r["comments"], "comment"))
        if r["liked"]:
            extra.append("you like it")
        print(f"{r['house']}/{r['post_id']}  {who}, {ago(r['at'])}: {one_line(r['text'], 200) or '(no text)'}"
              + (" [photo]" if r["photo"] else "") + (f"  ({', '.join(extra)})" if extra else ""))
        for c in json.loads(r["thread"] or "[]")[-2:]:
            print(f"    {c['name'] or c['house']}: {one_line(c['text'], 160)}")
    for house, problem in missed:
        print(why(house, problem))


def cmd_add(args):
    h = need_house(args, "friends add <house>")
    with db() as con:
        row = con.execute("select * from friends where house = ?", (h,)).fetchone()
    if row and row["state"] == "asked":
        return cmd_accept([h])
    if row and row["state"] == "friends":
        print(f"{label(h, row['name'])} and you are already friends.")
        return
    if row and row["state"] == "blocked":
        sys.exit(f"You blocked {h}. Unblock first: friends unblock {h}.")
    key = row["my_key"] if row and row["my_key"] else secrets.token_urlsafe(24)
    with db() as con:   # kept first: their house checks with this one while it answers
        con.execute("insert into friends (house, state, my_key, at) values (?, 'sent', ?, ?) "
                    "on conflict (house) do update set state = 'sent', my_key = excluded.my_key, at = excluded.at",
                    (h, key, now()))
    answer, problem = call(h, {"action": "request", "from": me(), "name": my_name(), "key": key})
    if not answer or answer.get("error"):
        with db() as con:
            con.execute("delete from friends where house = ? and state = 'sent'", (h,))
        err = (answer or {}).get("error")
        if err == "closed":
            sys.exit(f"{h} takes no friend requests.")
        if err == "unverified":
            sys.exit(f"{h} could not check this house back. Is this house's name right? ({me()})")
        sys.exit(why(h, problem) if problem else f"{h} did not take the request ({err}).")
    if answer.get("friends") and answer.get("key"):
        with db() as con:
            con.execute("update friends set state = 'friends', their_key = ?, name = ?, at = ? where house = ?",
                        (str(answer["key"])[:100], one_line(answer.get("name"), 60), now(), h))
        print(f"{label(h, one_line(answer.get('name'), 60))} and you are friends now.")
        return
    print(f"Asked {h} to be friends. Once they say yes, their friends-only posts come into your feed.")


def cmd_accept(args):
    h = need_house(args, "friends accept <house>")
    with db() as con:
        row = con.execute("select * from friends where house = ? and state = 'asked'", (h,)).fetchone()
    if not row:
        sys.exit(f"{h} has not asked to be friends. Open requests: friends requests.")
    key = secrets.token_urlsafe(24)
    answer, problem = call(h, {"action": "accept", "from": me(), "name": my_name(), "key": row["their_key"], "their": key})
    if not answer:
        sys.exit(why(h, problem))
    if answer.get("error"):
        with db() as con:
            con.execute("delete from friends where house = ?", (h,))
            con.execute("delete from news where kind = 'request' and house = ?", (h,))
        sys.exit(f"{h} no longer asks to be friends; the request is gone.")
    name = one_line(answer.get("name"), 60) or row["name"]
    with db() as con:
        con.execute("update friends set state = 'friends', my_key = ?, name = ?, at = ? where house = ?", (key, name, now(), h))
        con.execute("update news set seen = 1 where kind = 'request' and house = ?", (h,))
    print(f"{label(h, name)} and you are friends now: you see each other's friends-only posts.")


def cmd_decline(args):
    h = need_house(args, "friends decline <house>")
    with db() as con:
        row = con.execute("select * from friends where house = ? and state = 'asked'", (h,)).fetchone()
        if not row:
            sys.exit(f"{h} has not asked to be friends.")
        con.execute("delete from friends where house = ?", (h,))
        con.execute("delete from news where kind = 'request' and house = ?", (h,))
    call(h, {"action": "unfriend", "from": me(), "key": row["their_key"]})
    print(f"Declined {h}. They are not told why, only that there is no request any more.")


def cmd_remove(args):
    h = need_house(args, "friends remove <house>")
    with db() as con:
        row = con.execute("select * from friends where house = ? and state in ('friends', 'sent')", (h,)).fetchone()
        if not row:
            sys.exit(f"{h} is not a friend, and you did not ask them.")
        con.execute("delete from friends where house = ?", (h,))
        forget_feed(con, h)
    call(h, {"action": "unfriend", "from": me(), "key": row["my_key"]})
    if row["state"] == "sent":
        print(f"Took back your request to {h}.")
    else:
        print(f"{label(h, row['name'])} and you are no longer friends; neither sees the other's friends-only posts.")


def cmd_requests():
    with db() as con:
        asked = con.execute("select * from friends where state = 'asked' order by at").fetchall()
        sent = con.execute("select * from friends where state = 'sent' order by at").fetchall()
    if not asked and not sent:
        print("No open friend requests.")
        return
    for r in asked:
        print(f"{label(r['house'], r['name'])} wants to be friends ({ago(r['at'])}).")
    for r in sent:
        print(f"You asked {r['house']} ({ago(r['at'])}); no answer yet.")


def cmd_list():
    with db() as con:
        friends = con.execute("select * from friends where state = 'friends' order by lower(name), house").fetchall()
        follows = con.execute("select * from follows order by lower(name), house").fetchall()
        followers = con.execute("select * from followers order by lower(name), house").fetchall()
        blocked = con.execute("select house from friends where state = 'blocked' order by house").fetchall()
    print("Friends: " + (", ".join(label(r["house"], r["name"]) for r in friends) or "none yet") + ".")
    print("You follow: " + (", ".join(label(r["house"], r["name"]) for r in follows) or "nobody") + ".")
    print("Your followers: " + (", ".join(label(r["house"], r["name"]) for r in followers) or "none") + ".")
    if blocked:
        print("Blocked: " + ", ".join(r["house"] for r in blocked) + ".")


def cmd_follow(args, on):
    h = need_house(args, f"friends {'follow' if on else 'unfollow'} <house>")
    if on:
        profile, problem = call(h, {"action": "profile", "from": me()})
        if not profile or "name" not in profile:
            sys.exit(why(h, problem or "no wall"))
        name = one_line(profile.get("name"), 60)
        with db() as con:   # kept first: their house checks with this one
            con.execute("insert into follows (house, name, at) values (?, ?, ?) on conflict (house) do update set name = excluded.name",
                        (h, name, now()))
        call(h, {"action": "follow", "from": me(), "name": my_name()})
        print(f"You follow {label(h, name)}: their public posts come into your feed.")
        return
    with db() as con:
        gone = con.execute("delete from follows where house = ?", (h,)).rowcount
        forget_feed(con, h)
    if not gone:
        sys.exit(f"You do not follow {h}.")
    call(h, {"action": "follow", "from": me(), "name": my_name()})
    print(f"You no longer follow {h}.")


def cmd_profile(args):
    h = need_house(args, "friends profile <house>")
    with db() as con:
        row = con.execute("select * from friends where house = ? and state = 'friends'", (h,)).fetchone()
    payload = {"from": me()}
    if row:
        payload["key"] = row["their_key"]
    profile, problem = call(h, {"action": "profile", **payload})
    if not profile or "name" not in profile:
        sys.exit(why(h, problem or "no wall"))
    print(f"{label(h, one_line(profile.get('name'), 60))}, {wall_url(h)}")
    if profile.get("bio"):
        print(one_line(profile["bio"], 300))
    print(f"{plural(int(profile.get('posts') or 0), 'post')}, {plural(int(profile.get('friends') or 0), 'friend')}, "
          f"{plural(int(profile.get('followers') or 0), 'follower')}."
          + (" You are friends." if profile.get("friend") else ""))
    posts, _ = call(h, {"action": "posts", "limit": 5, **payload})
    for p in (posts or {}).get("posts") or []:
        if isinstance(p, dict):
            print(f"  {h}/{p.get('id')}  {ago(int(p.get('at') or 0))}: {one_line(p.get('text'), 200) or '(no text)'}"
                  + (" [photo]" if p.get("photo") else ""))


def cmd_like(args, on):
    house, n = ref(" ".join(args))
    if not house:
        sys.exit(f"friends {'like' if on else 'unlike'} <house>/<n>, like anna/12 (from friends feed).")
    if house == "me":
        sys.exit("That is your own post.")
    with db() as con:
        row = con.execute("select * from friends where house = ? and state = 'friends'", (house,)).fetchone()
    if not row:
        sys.exit(f"Only friends can like each other's posts, and {house} is not a friend yet (friends add {house}).")
    answer, problem = call(house, {"action": "like", "from": me(), "key": row["their_key"], "post": n, "on": on})
    if not answer:
        sys.exit(why(house, problem))
    if answer.get("error"):
        sys.exit(f"{house} has no post #{n} for you.")
    with db() as con:
        con.execute("update feed set liked = ?, likes = ? where house = ? and post_id = ?",
                    (1 if on else 0, int(answer.get("likes") or 0), house, n))
    print(f"You {'like' if on else 'no longer like'} {row['name'] or house}'s post #{n}.")


def cmd_comment(args):
    if len(args) < 2:
        sys.exit('friends comment <house>/<n> "<text>"')
    house, n = ref(args[0])
    text = clean(" ".join(args[1:]), MAX_COMMENT)
    if not house or not text:
        sys.exit('friends comment <house>/<n> "<text>", like: friends comment anna/12 "Beautiful!"')
    if house in ("me", me(False)):
        with db() as con:
            if not con.execute("select 1 from posts where id = ?", (n,)).fetchone():
                sys.exit(f"There is no post #{n} on your wall.")
            con.execute("insert into comments (post_id, house, name, text, at) values (?, ?, ?, ?, ?)",
                        (n, me(), my_name(), text, now()))
        print(f"Your comment is under your post #{n}.")
        return
    with db() as con:
        row = con.execute("select * from friends where house = ? and state = 'friends'", (house,)).fetchone()
    if not row:
        sys.exit(f"Only friends can comment on each other's posts, and {house} is not a friend yet.")
    answer, problem = call(house, {"action": "comment", "from": me(), "key": row["their_key"], "post": n, "text": text})
    if not answer:
        sys.exit(why(house, problem))
    if answer.get("error"):
        sys.exit(f"{house} has no post #{n} for you." if answer["error"] == "unknown" else f"{house} did not take the comment.")
    with db() as con:
        r = con.execute("select thread from feed where house = ? and post_id = ?", (house, n)).fetchone()
        if r:
            thread = json.loads(r["thread"] or "[]") + [{"house": me(), "name": my_name(), "text": text, "at": now()}]
            con.execute("update feed set comments = ?, thread = ? where house = ? and post_id = ?",
                        (int(answer.get("comments") or len(thread)), json.dumps(thread[-20:], ensure_ascii=False), house, n))
    print(f"Your comment is under {row['name'] or house}'s post #{n}.")


def cmd_block(args, on):
    h = need_house(args, f"friends {'block' if on else 'unblock'} <house>")
    with db() as con:
        row = con.execute("select * from friends where house = ?", (h,)).fetchone()
        if on:
            con.execute("insert into friends (house, name, state, at) values (?, ?, 'blocked', ?) on conflict (house) do "
                        "update set state = 'blocked', my_key = null, their_key = null", (h, row["name"] if row else "", now()))
            con.execute("delete from followers where house = ?", (h,))
            con.execute("delete from follows where house = ?", (h,))
            con.execute("delete from news where house = ?", (h,))
            forget_feed(con, h)
        elif not row or row["state"] != "blocked":
            sys.exit(f"{h} is not blocked.")
        else:
            con.execute("delete from friends where house = ?", (h,))
    if on and row and row["state"] in ("friends", "sent", "asked"):
        call(h, {"action": "unfriend", "from": me(), "key": row["my_key"] or row["their_key"]})
    print(f"Blocked {h}: no requests, follows, likes or comments from there, and they no longer see your friends-only posts."
          if on else f"{h} is no longer blocked.")


def cmd_avatar(args):
    if not args:
        sys.exit("friends avatar <file or https link>, or: friends avatar none")
    old = values().get("avatar", "")
    if args[0].lower() in ("none", "off", "remove"):
        new, said = "", "Your wall has no profile photo now."
    else:
        kind, raw = read_photo(args[0])
        with db() as con:
            new = str(keep_photo(con, kind, raw))
        said = "Your profile photo is on your wall."
    if str(old).isdigit():
        with db() as con:
            con.execute("delete from photos where id = ?", (int(old),))
    keep("avatar", new)
    print(said)


def cmd_photo(args):
    """For the window: one photo as JSON, of an own post or of a post in the feed (fetched once)."""
    house, n = (args[0].lower() if args else ""), (args[1] if len(args) > 1 else "")
    if house in ("me", me(False) or "me"):
        print(json.dumps(api_photo({"id": n}, owner=True)))
        return
    house = house_of(house)
    if not house or not (n == "avatar" or n.isdigit()):
        print(json.dumps({"error": "unknown"}))
        return
    with db() as con:
        row = con.execute("select * from feed_photos where house = ? and post_id = ?", (house, n)).fetchone()
        key = sources(con).get(house)
    if row:
        print(json.dumps({"type": row["type"], "data": base64.b64encode(row["data"]).decode()}))
        return
    payload = {"action": "photo", "id": n, "from": me()}
    if key:
        payload["key"] = key
    answer, _ = call(house, payload, timeout=15)
    try:
        raw = base64.b64decode(str((answer or {}).get("data") or ""), validate=True)
    except ValueError:
        raw = b""
    kind = kind_of(raw)
    if not kind or len(raw) > MAX_PHOTO:
        print(json.dumps({"error": "unknown"}))
        return
    with db() as con:
        con.execute("insert or replace into feed_photos (house, post_id, type, data, at) values (?, ?, ?, ?, ?)",
                    (house, n, kind, raw, now()))
    print(json.dumps({"type": kind, "data": base64.b64encode(raw).decode()}))


def cmd_data():
    """Everything the window shows at once, from this house only (the feed comes from friends feed --json)."""
    mine = me(False)
    v = values()
    with db() as con:
        wall = []
        for p in con.execute("select * from posts order by id desc limit 30").fetchall():
            j = post_json(con, p, {"house": mine or ""})
            j["liked_by"] = [l["name"] or l["house"] for l in con.execute("select * from likes where post_id = ? order by at", (p["id"],))]
            wall.append(j)
        out = {
            "me": {"house": mine or "", "name": my_name(), "bio": v["bio"], "link": wall_url(mine) if mine else "",
                   "avatar": bool(v.get("avatar")), "audience": v["audience"]},
            "news": [dict(n) | {"line": news_line(n)} for n in con.execute("select * from news order by id desc limit 15")],
            "asked": [dict(house=r["house"], name=r["name"], at=r["at"]) for r in con.execute("select * from friends where state = 'asked' order by at")],
            "sent": [dict(house=r["house"], at=r["at"]) for r in con.execute("select * from friends where state = 'sent' order by at")],
            "friends": [dict(house=r["house"], name=r["name"]) for r in con.execute("select * from friends where state = 'friends' order by lower(name), house")],
            "follows": [dict(house=r["house"], name=r["name"]) for r in con.execute("select * from follows order by lower(name), house")],
            "followers": [dict(house=r["house"], name=r["name"]) for r in con.execute("select * from followers order by lower(name), house")],
            "wall": wall,
            "feed": [feed_json(r, {h for h, k in sources(con).items() if k}) for r in feed_rows(con)],
        }
        con.execute("update news set seen = 1 where seen = 0 and kind != 'request'")
    print(json.dumps(out, ensure_ascii=False))


def cmd_settings(args):
    if not args:
        v = values()
        print(json.dumps({k: v[k] for k in DEFAULT}, ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in DEFAULT:
        sys.exit("friends settings set <" + "|".join(DEFAULT) + "> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "house":
        h = house_of(value)
        if value and not h:
            sys.exit(f"{value} is not a house name: lowercase letters, digits and -, like anna.")
        value = h or ""
    if key == "requests" and value not in ("on", "off"):
        sys.exit("requests is on or off.")
    if key == "audience" and value not in ("friends", "public"):
        sys.exit("audience is friends (only friends see new posts) or public (everyone).")
    if key == "name":
        value = one_line(value, 60)
    if key == "bio":
        value = clean(value, 300)
    keep(key, value)
    print(f"{key}: {value or 'cleared'}.")


def read_request():
    """The request of the wall, when the house runs this command for the route."""
    if sys.stdin is None or sys.stdin.isatty():
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.5)
    except (OSError, ValueError):
        ready = [sys.stdin]
    if not ready:
        return None
    raw = sys.stdin.read()
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) and "route" in data else None


def main(argv):
    if not argv or argv[0] == "api":
        request = read_request()
        if request is not None:
            print(json.dumps(api(request), ensure_ascii=False))
            return
        if argv:
            sys.exit("friends api reads the request of the wall on stdin.")
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    cmd, rest = (argv[0].lower(), argv[1:]) if argv else ("", [])
    commands = {
        "post": cmd_post, "wall": lambda a: cmd_wall(), "delete": cmd_delete, "feed": lambda a: cmd_feed(as_json),
        "add": cmd_add, "accept": cmd_accept, "decline": cmd_decline, "remove": cmd_remove, "unfriend": cmd_remove,
        "requests": lambda a: cmd_requests(), "list": lambda a: cmd_list(), "follow": lambda a: cmd_follow(a, True),
        "unfollow": lambda a: cmd_follow(a, False), "profile": cmd_profile, "like": lambda a: cmd_like(a, True),
        "unlike": lambda a: cmd_like(a, False), "comment": cmd_comment, "block": lambda a: cmd_block(a, True),
        "unblock": lambda a: cmd_block(a, False), "news": lambda a: cmd_news(), "avatar": cmd_avatar,
        "photo": cmd_photo, "data": lambda a: cmd_data(), "settings": cmd_settings,
        "link": lambda a: print(f"Your wall is at {wall_url(me())}. Anyone can open it and see your public posts; "
                                "friends see the rest in their own Iris."),
    }
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd in commands:
        commands[cmd](rest)
    else:
        sys.exit("friends post, friends feed, friends add <house>. `friends help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
