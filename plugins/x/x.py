#!/usr/bin/env python3
"""X (Twitter) for Iris, through the X API v2.

  x                         what is connected, and what still needs a link
  x koppel <client-id>      start the login; prints the URL to open (OAuth 2.0 with PKCE)
  x koppel --code <code|url>   finish the login with the code from the redirect
  x wie                     who the connected account is
  x tijdlijn [aantal]       the latest posts (default 5, between 5 and 100)
  x post "<tekst>"          make a draft; nothing is posted yet
  x post --ja <id>          publish that draft, only after your yes

X's API is paid: you buy API credits in the X Developer Console. Without paid access, calls usually
fail (older free/basic plans were limited or read-only), so reading may work while posting needs a
paid plan. The app secret, if you have one, stays in the vault (kluis); this tool never prints a token.
Nothing goes out before you approve the exact text on screen.
"""

import base64
import hashlib
import json
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

API = "https://api.x.com/2"
AUTH = "https://x.com/i/oauth2/authorize"
TOKEN = "https://api.x.com/2/oauth2/token"
# Register this exact URL as a Callback URL in the X app. The browser cannot reach this house, so the
# owner copies the code out of the address bar; see README.md.
REDIRECT = "http://localhost:8765/callback"
SCOPES = ["tweet.read", "users.read", "tweet.write", "offline.access"]

VAULT_ITEM = "x-api"
VAULT_DOMAIN = "x.com"
DRAFT_TTL = 3600


def fail(text):
    print(f"x: {text}")
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
    p = shutil.which("kluis") or shutil.which("vault")
    if p:
        return p
    p = os.path.expanduser("~/.local/bin/kluis")
    return p if os.path.isfile(p) else None


def vault_has(item):
    exe = vault_bin()
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in r.stdout.splitlines():
        name = line.split("\t")[0].strip().split("  ")[0].strip()
        if name == item:
            return True
    return False


def store_secret_optional():
    """A Native App (public client) has no secret; then this is skipped quietly."""
    if vault_has(VAULT_ITEM) or not vault_bin():
        return
    try:
        subprocess.run([vault_bin(), "vraag", VAULT_ITEM, "--domein", VAULT_DOMAIN,
                        "X API client secret (optional for a Native App; leave empty and cancel if you have none)"],
                       capture_output=True, text=True, timeout=200)
    except (OSError, subprocess.TimeoutExpired):
        pass


# ---------------------------------------------------------------- http

def redact(text, *secrets_):
    text = str(text)
    for s in secrets_:
        if s:
            text = text.replace(str(s), "***")
    return text


def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except OSError as e:
        return 0, str(e)


def x_error(body):
    try:
        d = json.loads(body)
    except ValueError:
        return body
    if isinstance(d, dict):
        if d.get("detail"):
            return d["detail"] + (f" ({d.get('title')})" if d.get("title") else "")
        if d.get("errors"):
            first = d["errors"][0]
            if isinstance(first, dict):
                return first.get("detail") or first.get("message") or str(first)
        if d.get("error"):
            return d["error"]
    return body


def api(method, path, token=None, params=None, json_body=None, form=None, headers=None):
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    url = API + path
    data = None
    if method == "GET":
        if params:
            url += "?" + urllib.parse.urlencode(params)
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body is not None:
        data = json.dumps(json_body).encode()
        h["Content-Type"] = "application/json"
    status, body = http(method, url, data=data, headers=h)
    try:
        d = json.loads(body)
    except ValueError:
        d = None
    if status >= 400:
        raise RuntimeError(x_error(body))
    return d if d is not None else body


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
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{AUTH}?{q}"


def start_link(client_id, force=False):
    st = load_state()
    st["client_id"] = client_id
    verifier, challenge = pkce()
    st["code_verifier"] = verifier
    st["oauth_state"] = secrets.token_urlsafe(24)
    if force:
        for k in ("access_token", "refresh_token", "expires_at", "user_id", "username", "name"):
            st.pop(k, None)
    save_state(st)
    store_secret_optional()
    print(f"X app client id: {client_id} (saved).")
    print()
    print("Open this URL and approve access for your X account:")
    print(auth_url(client_id, st["oauth_state"], challenge))
    print()
    print("X sends you to a localhost page that cannot load here; that is expected. Copy the whole")
    print("address bar and run this within about 30 seconds (X expires the code quickly):")
    print('  x koppel --code "<paste the whole URL or just the code>"')
    print(f"Make sure {REDIRECT} is registered as a Callback URL in your X app.")


def finish_link(pasted):
    st = load_state()
    client_id = st.get("client_id")
    verifier = st.get("code_verifier")
    if not client_id or not verifier:
        fail("no login in progress. Run `x koppel <client-id>` first.")
    code = parse_param(pasted, "code") or (pasted.strip() if pasted and "=" not in pasted else None)
    if not code:
        err = parse_param(pasted, "error_description") or parse_param(pasted, "error")
        fail("no code in that paste" + (f": {err}" if err else "") +
             '. Copy the whole redirect URL, or just the "code" value.')
    got_state = parse_param(pasted, "state")
    if got_state and st.get("oauth_state") and got_state != st["oauth_state"]:
        fail("the login state does not match. Run `x koppel <client-id>` again for a fresh URL.")

    status, body = http("POST", TOKEN,
                        data=urllib.parse.urlencode({
                            "code": code,
                            "grant_type": "authorization_code",
                            "client_id": client_id,
                            "redirect_uri": REDIRECT,
                            "code_verifier": verifier,
                        }).encode(),
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        d = json.loads(body)
    except ValueError:
        d = {}
    if status >= 400 or "access_token" not in d:
        fail("the code could not be exchanged: " + x_error(body))
    st["access_token"] = d["access_token"]
    if d.get("refresh_token"):
        st["refresh_token"] = d["refresh_token"]
    st["expires_at"] = int(time.time()) + int(d.get("expires_in") or 7200)
    st["scope"] = d.get("scope")
    save_state(st)
    me = api("GET", "/users/me", token=st["access_token"],
             params={"user.fields": "username,name"})
    data = me.get("data", me) if isinstance(me, dict) else {}
    st["user_id"] = data.get("id")
    st["username"] = data.get("username")
    st["name"] = data.get("name")
    save_state(st)
    print(f"Connected as @{data.get('username') or st['user_id']} ({data.get('name') or ''}).".strip())


def ensure_token():
    st = load_state()
    token = st.get("access_token")
    if not token:
        fail("not connected. Run `x koppel <client-id>` first.")
    if st.get("expires_at") and int(st["expires_at"]) - int(time.time()) > 60:
        return token
    refresh = st.get("refresh_token")
    if not refresh:
        fail("the access token has expired and there is no refresh token. Run `x koppel <client-id>` again.")
    status, body = http("POST", TOKEN,
                        data=urllib.parse.urlencode({
                            "grant_type": "refresh_token",
                            "refresh_token": refresh,
                            "client_id": st["client_id"],
                        }).encode(),
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        d = json.loads(body)
    except ValueError:
        d = {}
    if status >= 400 or "access_token" not in d:
        fail("could not refresh the token: " + x_error(body))
    st["access_token"] = d["access_token"]
    if d.get("refresh_token"):
        st["refresh_token"] = d["refresh_token"]
    st["expires_at"] = int(time.time()) + int(d.get("expires_in") or 7200)
    save_state(st)
    return st["access_token"]


# ---------------------------------------------------------------- drafts

def new_draft(text):
    st = load_state()
    did = secrets.token_hex(3)
    st.setdefault("pending", {})[did] = {"text": text, "ts": int(time.time())}
    save_state(st)
    return did


def take_draft(did):
    st = load_state()
    d = (st.get("pending") or {}).get(did)
    if not d:
        fail(f"no draft {did}. Make one first, e.g. x post \"...\"")
    if int(time.time()) - int(d.get("ts", 0)) > DRAFT_TTL:
        st["pending"].pop(did, None)
        save_state(st)
        fail(f"draft {did} is more than an hour old; make a fresh one.")
    st["pending"].pop(did, None)
    save_state(st)
    return d


def status():
    st = load_state()
    print("X (Twitter): read your timeline and post, through the X API v2.")
    print()
    if not st.get("client_id"):
        print("Not set up yet. You need:")
        print("  1. an app in the X Developer Console (developer.x.com) with OAuth 2.0")
        print(f"  2. the exact Callback URL {REDIRECT} in the app settings")
        print("  3. a paid plan or API credits: X's API is pay-per-use, and posting needs paid access")
        print()
        print("Then run: x koppel <client-id>")
        return
    print(f"App client id: {st['client_id']}")
    if not st.get("access_token"):
        print("Not connected. Run: x koppel " + st["client_id"])
        return
    who = f"@{st.get('username')}" if st.get("username") else st.get("user_id", "?")
    print(f"Connected as {who} ({st.get('name') or 'X account'})")
    print("Reminder: X's API is paid. Without a paid plan or credits, reading may fail and posting "
          "usually will; check your plan in the X Developer Console.")
    print()
    print("Commands: x wie, x tijdlijn [aantal], x post \"<text>\"")


def who():
    token = ensure_token()
    me = api("GET", "/users/me", token=token,
             params={"user.fields": "username,name,description,public_metrics"})
    d = me.get("data", me) if isinstance(me, dict) else {}
    print(f"@{d.get('username')} ({d.get('name') or ''}) - id {d.get('id')}")
    if d.get("description"):
        print(d["description"])
    m = d.get("public_metrics") or {}
    if m:
        print(f"followers {m.get('followers_count', '?')}, following {m.get('following_count', '?')}, "
              f"posts {m.get('tweet_count', '?')}")


def timeline(rest):
    token = ensure_token()
    st = load_state()
    uid = st.get("user_id")
    if not uid:
        me = api("GET", "/users/me", token=token, params={"user.fields": "username"})
        uid = (me.get("data", me) if isinstance(me, dict) else {}).get("id")
        st["user_id"] = uid
        save_state(st)
    n = 5
    if rest:
        try:
            n = int(rest[0])
        except ValueError:
            fail("give a number, e.g. x tijdlijn 10")
    n = max(5, min(100, n))
    d = api("GET", f"/users/{uid}/tweets", token=token,
            params={"max_results": n, "tweet.fields": "created_at,public_metrics"})
    rows = d.get("data") or []
    if not rows:
        print("no posts on this timeline")
        return
    for t in rows:
        when = (t.get("created_at") or "")[:16].replace("T", " ")
        print(f"{when}  {t.get('text', '').replace(chr(10), ' ')[:140]}")
        print(f"    https://x.com/i/status/{t.get('id')}")


def post(rest):
    if "--ja" in rest:
        i = rest.index("--ja")
        did = rest[i + 1] if i + 1 < len(rest) else None
        if not did:
            fail("use: x post --ja <draft-id>")
        d = take_draft(did)
        token = ensure_token()
        r = api("POST", "/tweets", token=token, json_body={"text": d["text"]})
        data = r.get("data", r) if isinstance(r, dict) else {}
        tid = data.get("id", "?")
        print(f"posted on X: https://x.com/i/status/{tid}")
        return
    st = load_state()
    if not st.get("access_token"):
        fail("not connected. Run `x koppel <client-id>` first.")
    text = " ".join(rest).strip()
    if not text:
        fail('use: x post "<text>"')
    if len(text) > 280:
        print(f"note: this is {len(text)} characters; X allows 280 for most accounts.")
    did = new_draft(text)
    print(f"DRAFT {did} - nothing has been posted.")
    print()
    print(text)
    print()
    print("Show this on screen and only continue after the owner says yes:")
    print(f"  x post --ja {did}")


def main():
    a = sys.argv[1:]
    if not a:
        status()
        return
    if a[0] == "koppel":
        rest = a[1:]
        if "--code" in rest:
            i = rest.index("--code")
            if i + 1 >= len(rest):
                fail('use: x koppel --code "<code or redirected URL>"')
            finish_link(rest[i + 1])
        elif "--opnieuw" in rest:
            st = load_state()
            cid = st.get("client_id")
            if not cid:
                fail("no app yet. Run `x koppel <client-id>` first.")
            start_link(cid, force=True)
        elif rest and not rest[0].startswith("--"):
            start_link(rest[0])
        else:
            st = load_state()
            if st.get("client_id"):
                start_link(st["client_id"])
            else:
                print("Give your X app client id: x koppel <client-id>\n"
                      "Create the app at developer.x.com, enable OAuth 2.0, and add the callback "
                      f"{REDIRECT}.")
    elif a[0] == "wie":
        who()
    elif a[0] == "tijdlijn":
        timeline(a[1:])
    elif a[0] == "post":
        post(a[1:])
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        fail(str(e))
    except KeyboardInterrupt:
        print("\nx: stopped")
        sys.exit(1)
