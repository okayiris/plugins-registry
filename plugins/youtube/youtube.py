#!/usr/bin/env python3
"""YouTube for Iris: search, read videos and channels, and upload with your own Google app.

Reading uses your own YouTube Data API key, which stays in the vault:

  youtube                          what is set up, and what is still missing
  youtube key ask                  ask for your YouTube Data API key (it goes into the vault)
  youtube key                      which vault item is used, never the key itself
  youtube search "<query>" [-n 5]  search videos
  youtube video <id or url>        title, channel, duration, views and likes
  youtube channel <id or @handle>  channel details and subscriber count

Uploading uses OAuth with your own Google OAuth client:

  youtube connect <client-id>      start the login; prints the URL to open
  youtube code <code or url>       finish the login with the code from the redirect
  youtube secret ask               put your OAuth client secret in the vault (if your app has one)
  youtube who                      which Google account is connected
  youtube upload <file> --title "..." [--description ...] [--tags a,b]
                       [--privacy private|unlisted|public] [--category 22]
                                   make a draft; nothing is uploaded yet
  youtube upload --yes <id>        upload that draft, only after your yes

The API key and the OAuth client secret stay in the vault and are never read by this tool. The
reads are made by the vault with the key filled in as {g}. OAuth tokens are kept in .state.json
next to the plugin, readable only by you.
"""

import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(HERE, ".state.json")

API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REDIRECT = "http://localhost:8765/callback"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]

KEY_ITEM = "youtube"
KEY_DOMAIN = "www.googleapis.com"
SECRET_ITEM = "youtube-oauth"
SECRET_DOMAIN = "oauth2.googleapis.com"
DRAFT_TTL = 3600


def fail(text):
    print(f"youtube: {text}")
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


def key_item():
    return item_for(KEY_ITEM, KEY_DOMAIN)


def secret_item():
    return item_for(SECRET_ITEM, SECRET_DOMAIN)


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


def vault_call(item, method, url, body=None, timeout=60):
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system.")
    cmd = [exe, "doe", item, method, url]
    if body is not None:
        cmd.append(body)
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


# ---------------------------------------------------------------- http

def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except OSError as e:
        return 0, str(e)


def api_error(body):
    try:
        d = json.loads(body)
    except ValueError:
        return str(body)
    err = d.get("error") if isinstance(d, dict) else None
    if isinstance(err, dict):
        return err.get("message") or str(err)
    if isinstance(err, str):
        return err
    if isinstance(d, dict) and d.get("error_description"):
        return d["error_description"]
    return str(body)


def read_api(path, params):
    item = key_item()
    if not item:
        fail('no YouTube Data API key in the vault yet. Run `youtube key ask` first.')
    url = API + path + "?" + urllib.parse.urlencode(params) + "&key={g}"
    status, text = vault_call(item, "GET", url)
    try:
        data = json.loads(text)
    except ValueError:
        fail(f"YouTube returned an unreadable answer (status {status}).")
    if status >= 400:
        fail(f"YouTube: {api_error(text)}")
    return data


# ---------------------------------------------------------------- formatting

def human_duration(text):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text or "")
    if not m:
        return text or "?"
    days, hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    total = days * 24 + hours
    if total:
        return f"{total}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def video_id(value):
    value = value.strip()
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", value)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    return value


def channel_lookup(value):
    value = value.strip()
    m = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]+)", value)
    if m:
        return "id", m.group(1)
    m = re.search(r"youtube\.com/@([A-Za-z0-9_.-]+)", value)
    if m:
        return "forHandle", "@" + m.group(1)
    if value.startswith("@"):
        return "forHandle", value
    if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", value):
        return "id", value
    return "forHandle", "@" + value


# ---------------------------------------------------------------- reads

def cmd_key(args):
    if args and args[0] == "ask":
        print("A window opens to paste your YouTube Data API key; it goes straight into the vault.")
        vault_ask(KEY_ITEM, KEY_DOMAIN,
                  "YouTube Data API key (enable YouTube Data API v3 on it)")
        return
    item = key_item()
    if not item:
        print("No YouTube Data API key in the vault yet. Run: youtube key ask")
        return
    print(f'Using the vault item "{item}" for {KEY_DOMAIN}. The key itself is never shown.')


def cmd_search(args):
    n = 5
    free = []
    i = 0
    while i < len(args):
        if args[i] in ("-n", "--n") and i + 1 < len(args):
            try:
                n = max(1, min(50, int(args[i + 1])))
            except ValueError:
                fail("-n needs a number")
            i += 2
            continue
        free.append(args[i])
        i += 1
    query = " ".join(free).strip()
    if not query:
        fail('use: youtube search "<query>" [-n 5]')
    data = read_api("/search", {
        "part": "snippet", "type": "video", "maxResults": n, "q": query,
    })
    rows = data.get("items") or []
    if not rows:
        print(f'No videos found for "{query}".')
        return
    for it in rows:
        sn = it.get("snippet") or {}
        vid = (it.get("id") or {}).get("videoId")
        print(f"{sn.get('title', '?')}")
        print(f"  {sn.get('channelTitle', '?')}  https://youtu.be/{vid}")


def cmd_video(args):
    if not args:
        fail("use: youtube video <id or url>")
    vid = video_id(args[0])
    data = read_api("/videos", {
        "part": "snippet,statistics,contentDetails", "id": vid,
    })
    rows = data.get("items") or []
    if not rows:
        fail(f'no video with id "{vid}".')
    it = rows[0]
    sn = it.get("snippet") or {}
    st = it.get("statistics") or {}
    cd = it.get("contentDetails") or {}
    print(f"{sn.get('title', '?')}")
    print(f"  channel:  {sn.get('channelTitle', '?')}")
    print(f"  published:{str(sn.get('publishedAt', '?'))[:10]}   duration: {human_duration(cd.get('duration'))}")
    print(f"  views: {st.get('viewCount', '?')}  likes: {st.get('likeCount', '?')}  "
          f"comments: {st.get('commentCount', '?')}")
    print(f"  https://youtu.be/{it.get('id')}")
    desc = (sn.get("description") or "").strip().replace("\n", " ")
    if desc:
        print(f"  {desc[:200]}")


def cmd_channel(args):
    if not args:
        fail("use: youtube channel <id or @handle>")
    field, value = channel_lookup(args[0])
    data = read_api("/channels", {
        "part": "snippet,statistics", field: value,
    })
    rows = data.get("items") or []
    if not rows:
        fail(f'no channel found for "{args[0]}".')
    it = rows[0]
    sn = it.get("snippet") or {}
    st = it.get("statistics") or {}
    print(f"{sn.get('title', '?')}  ({it.get('id')})")
    print(f"  subscribers: {st.get('subscriberCount', '?')}  videos: {st.get('videoCount', '?')}  "
          f"views: {st.get('viewCount', '?')}")
    if sn.get("customUrl"):
        print(f"  {sn['customUrl']}")
    desc = (sn.get("description") or "").strip().replace("\n", " ")
    if desc:
        print(f"  {desc[:200]}")


# ---------------------------------------------------------------- oauth

def parse_param(text, key):
    m = re.search(r"[?&#]" + re.escape(key) + r"=([^&#\s]+)", text or "")
    return urllib.parse.unquote(m.group(1)) if m else None


def pkce():
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def auth_url(client_id, state, challenge):
    q = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{AUTH}?{q}"


def cmd_secret(args):
    if args and args[0] == "ask":
        print("A window opens to paste your Google OAuth client secret; it goes straight into the vault.")
        vault_ask(SECRET_ITEM, SECRET_DOMAIN,
                  "Google OAuth client secret for the YouTube upload app")
        return
    item = secret_item()
    if not item:
        print("No OAuth client secret in the vault. Run: youtube secret ask")
        return
    print(f'Using the vault item "{item}" for {SECRET_DOMAIN}.')


def cmd_connect(args):
    if not args or args[0].startswith("--"):
        st = load_state()
        client_id = st.get("client_id")
        if not client_id:
            fail("use: youtube connect <client-id> (from your own Google OAuth app)")
    else:
        client_id = args[0]
    st = load_state()
    st["client_id"] = client_id
    verifier, challenge = pkce()
    st["code_verifier"] = verifier
    st["oauth_state"] = secrets.token_urlsafe(24)
    for k in ("access_token", "refresh_token", "expires_at"):
        st.pop(k, None)
    save_state(st)
    if not secret_item():
        print("Tip: if your Google OAuth app has a client secret, put it in the vault first:")
        print("  youtube secret ask")
        print()
    print(f"Google OAuth client id: {client_id} (saved).")
    print()
    print("Open this URL and approve access for your Google account:")
    print(auth_url(client_id, st["oauth_state"], challenge))
    print()
    print("Google sends you to a localhost page that cannot load here; that is expected. Copy the")
    print("whole address bar and run this within about a minute:")
    print('  youtube code "<paste the whole URL or just the code>"')
    print(f"Make sure {REDIRECT} is registered as a redirect URI in your Google OAuth client.")


def token_request(form):
    """Exchange or refresh. Uses the vault when a client secret is set, so it never enters this process."""
    item = secret_item()
    if item:
        payload = dict(form)
        payload["client_secret"] = "{g}"
        status, text = vault_call(item, "POST", TOKEN, body=json.dumps(payload))
        if status == 0:
            fail(text)
        return text
    status, text = http("POST", TOKEN, data=urllib.parse.urlencode(form).encode(),
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    if status == 0:
        fail(text)
    return text


def cmd_code(args):
    if not args:
        fail('use: youtube code "<code or redirected URL>"')
    pasted = args[0]
    st = load_state()
    client_id = st.get("client_id")
    verifier = st.get("code_verifier")
    if not client_id or not verifier:
        fail("no login in progress. Run `youtube connect <client-id>` first.")
    code = parse_param(pasted, "code") or (pasted.strip() if pasted and "=" not in pasted else None)
    if not code:
        err = parse_param(pasted, "error_description") or parse_param(pasted, "error")
        fail("no code in that paste" + (f": {err}" if err else ""))
    got_state = parse_param(pasted, "state")
    if got_state and st.get("oauth_state") and got_state != st["oauth_state"]:
        fail("the login state does not match. Run `youtube connect <client-id>` again.")

    text = token_request({
        "code": code,
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "code_verifier": verifier,
    })
    try:
        d = json.loads(text)
    except ValueError:
        fail("the code could not be exchanged: " + str(text))
    if "access_token" not in d:
        fail("the code could not be exchanged: " + api_error(text))
    st["access_token"] = d["access_token"]
    if d.get("refresh_token"):
        st["refresh_token"] = d["refresh_token"]
    st["expires_at"] = int(time.time()) + int(d.get("expires_in") or 3600)
    st["scope"] = d.get("scope")
    save_state(st)
    cmd_who([])


def ensure_token():
    st = load_state()
    token = st.get("access_token")
    if not token:
        fail("not connected for upload. Run `youtube connect <client-id>` first.")
    if st.get("expires_at") and int(st["expires_at"]) - int(time.time()) > 60:
        return token
    refresh = st.get("refresh_token")
    if not refresh:
        fail("the access token expired and there is no refresh token. Run `youtube connect` again.")
    text = token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": st["client_id"],
    })
    try:
        d = json.loads(text)
    except ValueError:
        fail("could not refresh the token: " + str(text))
    if "access_token" not in d:
        fail("could not refresh the token: " + api_error(text))
    st["access_token"] = d["access_token"]
    st["expires_at"] = int(time.time()) + int(d.get("expires_in") or 3600)
    save_state(st)
    return st["access_token"]


def cmd_who(args):
    token = ensure_token()
    status, text = http("GET", API + "/channels?part=snippet&mine=true",
                        headers={"Authorization": f"Bearer {token}"})
    if status >= 400 or status == 0:
        fail("Google refused the token: " + api_error(text))
    try:
        d = json.loads(text)
    except ValueError:
        fail("Google returned an unreadable answer.")
    rows = d.get("items") or []
    if not rows:
        print("Connected, but this Google account has no YouTube channel.")
        return
    sn = rows[0].get("snippet") or {}
    print(f"Connected as {sn.get('title', '?')} ({rows[0].get('id')}).")


# ---------------------------------------------------------------- upload

def new_draft(meta):
    st = load_state()
    did = secrets.token_hex(3)
    st.setdefault("pending", {})[did] = dict(meta, ts=int(time.time()))
    save_state(st)
    return did


def take_draft(did):
    st = load_state()
    d = (st.get("pending") or {}).get(did)
    if not d:
        fail(f"no draft {did}. Make one first: youtube upload <file> --title \"...\"")
    if int(time.time()) - int(d.get("ts", 0)) > DRAFT_TTL:
        st["pending"].pop(did, None)
        save_state(st)
        fail(f"draft {did} is more than an hour old; make a fresh one.")
    st["pending"].pop(did, None)
    save_state(st)
    return d


def cmd_upload(args):
    if "--yes" in args:
        i = args.index("--yes")
        did = args[i + 1] if i + 1 < len(args) else None
        if not did:
            fail("use: youtube upload --yes <draft-id>")
        meta = take_draft(did)
        token = ensure_token()
        path = meta["file"]
        if not os.path.isfile(path):
            fail(f"the file is gone: {path}")
        try:
            with open(path, "rb") as f:
                media = f.read()
        except OSError as exc:
            fail(str(exc))
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        boundary = "yt" + secrets.token_hex(12)
        payload = {
            "snippet": {
                "title": meta["title"],
                "description": meta.get("description", ""),
                "tags": meta.get("tags", []),
                "categoryId": str(meta.get("category", 22)),
            },
            "status": {
                "privacyStatus": meta.get("privacy", "unlisted"),
                "selfDeclaredMadeForKids": False,
            },
        }
        body = b"".join([
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
            json.dumps(payload).encode(),
            b"\r\n",
            f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode(),
            media,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        url = UPLOAD + "?uploadType=multipart&part=snippet,status"
        status, text = http("POST", url, data=body, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        })
        if status >= 400 or status == 0:
            fail("upload failed: " + api_error(text))
        try:
            d = json.loads(text)
        except ValueError:
            fail("YouTube returned an unreadable answer after the upload.")
        vid = d.get("id", "?")
        print(f'uploaded ({payload["status"]["privacyStatus"]}): https://youtu.be/{vid}')
        return

    privacy = "unlisted"
    title = None
    description = ""
    tags = []
    category = 22
    free = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--title" and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif a == "--description" and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        elif a == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",") if t.strip()]
            i += 2
        elif a == "--privacy" and i + 1 < len(args):
            privacy = args[i + 1].lower()
            i += 2
        elif a == "--category" and i + 1 < len(args):
            try:
                category = int(args[i + 1])
            except ValueError:
                fail("--category needs a number, e.g. 22")
            i += 2
        else:
            free.append(a)
            i += 1
    if privacy not in ("private", "unlisted", "public"):
        fail("--privacy must be private, unlisted or public.")
    if not free:
        fail('use: youtube upload <file> --title "..." [--description ...] [--privacy ...]')
    path = os.path.abspath(os.path.expanduser(free[0]))
    if not os.path.isfile(path):
        fail(f"no file at {path}")
    if not title:
        title = os.path.splitext(os.path.basename(path))[0]
    if not ensure_login():
        return
    did = new_draft({
        "file": path, "title": title, "description": description,
        "tags": tags, "privacy": privacy, "category": category,
    })
    size = os.path.getsize(path)
    print(f"DRAFT {did} - nothing has been uploaded.")
    print()
    print(f"  file:     {path} ({size / (1024 * 1024):.1f} MB)")
    print(f"  title:    {title}")
    print(f"  privacy:  {privacy}")
    if description:
        print(f"  text:     {description[:200]}")
    print()
    print("Only continue after the owner says yes:")
    print(f"  youtube upload --yes {did}")


def ensure_login():
    st = load_state()
    if st.get("access_token") or st.get("refresh_token"):
        return True
    print("Uploading needs a one-time login with your own Google OAuth app:")
    print("  1. youtube connect <client-id>")
    print("  2. approve in the browser and run: youtube code \"<redirect URL>\"")
    print()
    print("Reading videos and channels already works with just the API key; run: youtube key ask")
    return False


# ---------------------------------------------------------------- status

def status():
    print("YouTube: search and read videos and channels, and upload with your own Google app.")
    print()
    item = key_item()
    if item:
        print(f'Reads: vault item "{item}" (YouTube Data API key).')
    else:
        print("Reads: no API key yet. Run: youtube key ask")
    st = load_state()
    if st.get("access_token") or st.get("refresh_token"):
        print(f"Upload: connected as a Google account (client id {st.get('client_id', '?')}).")
    else:
        print("Upload: not connected. Run: youtube connect <client-id>")
    if not item:
        print()
        print("For reading you need:")
        print("  1. a Google Cloud project")
        print("  2. the YouTube Data API v3 enabled under APIs & Services > Library")
        print("  3. an API key under APIs & Services > Credentials")
        print()
        print("Then run: youtube key ask")
    print()
    print('Try: youtube search "<query>"  |  youtube video <id>  |  youtube channel <@handle>')


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
    elif cmd == "secret":
        cmd_secret(a[1:])
    elif cmd == "search":
        cmd_search(a[1:])
    elif cmd == "video":
        cmd_video(a[1:])
    elif cmd == "channel":
        cmd_channel(a[1:])
    elif cmd == "connect":
        cmd_connect(a[1:])
    elif cmd == "code":
        cmd_code(a[1:])
    elif cmd == "who":
        cmd_who(a[1:])
    elif cmd == "upload":
        cmd_upload(a[1:])
    else:
        status()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nyoutube: stopped")
        sys.exit(1)
