#!/usr/bin/env python3
"""Socials for Iris: Facebook Pages and Instagram, through the Meta Graph API.

  socials                              what is connected, and what still needs a link
  socials koppel <client-id>           start the Meta login; prints the URL to open
  socials koppel --code <code|url>     finish the login with the code from the redirect
  socials koppel --pagina <page-id>    choose which Facebook Page to use
  socials facebook lijst [--max N]     the latest posts on the Page
  socials facebook post "<tekst>"      make a draft; nothing is published yet
  socials facebook post --ja <id>      publish that draft, only after your yes
  socials instagram lijst [--max N]    the latest media on Instagram
  socials instagram post "<tekst>" [--beeld URL]   make a draft
  socials instagram post --ja <id>     publish that draft, only after your yes

Instagram needs a Business or Creator account linked to a Facebook Page. The app secret lives in the
vault (kluis); this tool never sees it and never prints a token. Nothing goes out before you approve
the exact text on screen.
"""

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

# The current Graph API version, checked against the Meta docs (v26.0, Sep 2026).
GRAPH_VERSION = "v26.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
LOGIN_VERSION = "v26.0"
LOGIN = f"https://www.facebook.com/{LOGIN_VERSION}/dialog/oauth"
# Facebook's documented redirect for desktop/manual login. The owner copies the code back.
REDIRECT = "https://www.facebook.com/connect/login_success.html"
SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_content_publish",
    "business_management",
]

VAULT_ITEM = "socials-meta"
VAULT_DOMAIN = "facebook.com"
DRAFT_TTL = 3600  # a draft must be approved within an hour


def fail(text):
    print(f"socials: {text}")
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


def vault_ask(item, uitleg, gebruiker=None):
    """Let the owner paste a secret into the vault window. Returns (ok, message)."""
    exe = vault_bin()
    if not exe:
        return False, "the vault command (kluis) is not available"
    args = [exe, "vraag", item, "--domein", VAULT_DOMAIN, uitleg]
    if gebruiker:
        args += ["--gebruiker", gebruiker]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=200)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    out = (r.stdout or r.stderr or "").strip()
    return r.returncode == 0, out


def vault_do(method, url):
    """Make a call through the vault, with {g} replaced by the app secret. The secret is never seen."""
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not available; a Meta app secret is needed")
    try:
        r = subprocess.run([exe, "doe", VAULT_ITEM, method, url],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        fail(f"the vault did not answer ({e})")
    out = r.stdout or ""
    m = re.match(r"\s*status\s+(\d+)\s*\n?", out)
    if not m:
        fail((r.stderr or out or "the vault refused the call").strip())
    status = int(m.group(1))
    body = out[m.end():].strip()
    return status, body


def ensure_secret(force=False):
    if not force and vault_has(VAULT_ITEM):
        return True
    ok, msg = vault_ask(VAULT_ITEM, "Meta app secret for the socials plugin (Facebook Login for Business)")
    if not ok:
        fail("the app secret is not in the vault: " + (msg or "cancelled") +
             "\nRun `kluis vraag socials-meta --domein facebook.com \"Meta app secret\"` and try again.")
    return True


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


def graph_error(body):
    try:
        d = json.loads(body)
        e = d.get("error") or {}
        msg = e.get("message") or body
        code = e.get("code")
        return f"{msg} (code {code})" if code else msg
    except (ValueError, AttributeError):
        return body


def graph(method, path, token=None, params=None):
    params = dict(params or {})
    if token:
        params["access_token"] = token
    url = GRAPH + path
    data = None
    if method == "GET":
        if params:
            url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    status, body = http(method, url, data=data)
    try:
        d = json.loads(body)
    except ValueError:
        d = None
    if status >= 400 or (isinstance(d, dict) and "error" in d):
        raise RuntimeError(graph_error(body))
    return d if d is not None else body


# ---------------------------------------------------------------- oauth

def parse_param(text, key):
    m = re.search(r"[?&#]" + re.escape(key) + r"=([^&#\s]+)", text or "")
    return urllib.parse.unquote(m.group(1)) if m else None


def auth_url(client_id, state):
    q = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "state": state,
        "response_type": "code",
        "scope": " ".join(SCOPES),
    })
    return f"{LOGIN}?{q}"


def start_link(client_id, force=False):
    st = load_state()
    st["client_id"] = client_id
    st["oauth_state"] = secrets.token_urlsafe(24)
    if force:
        for k in ("user_token", "page_token", "page_id", "page_name", "ig_user_id", "ig_username"):
            st.pop(k, None)
    save_state(st)
    ensure_secret(force=False)
    print("Meta app: " + client_id + " (saved). App secret is in the vault.")
    print()
    print("Open this URL and log in with the Facebook account that manages your Page:")
    print(auth_url(client_id, st["oauth_state"]))
    print()
    print("Facebook sends you to a page that may look empty. Copy the whole address bar and run:")
    print('  socials koppel --code "<paste the whole URL or just the code>"')
    print("The code is valid for about ten minutes; the redirect URL is " + REDIRECT)


def finish_link(pasted):
    st = load_state()
    client_id = st.get("client_id")
    if not client_id:
        fail("no app yet. Run `socials koppel <client-id>` first.")
    code = parse_param(pasted, "code") or (pasted.strip() if pasted and "=" not in pasted else None)
    if not code:
        err = parse_param(pasted, "error_description") or parse_param(pasted, "error")
        fail("no code in that paste" + (f": {err}" if err else "") +
             '. Copy the whole redirect URL, or just the "code" value.')
    got_state = parse_param(pasted, "state")
    if got_state and st.get("oauth_state") and got_state != st["oauth_state"]:
        fail("the login state does not match. Run `socials koppel <client-id>` again for a fresh URL.")
    ensure_secret()

    # 1. code -> short-lived user token, done inside the vault so the secret stays there
    url = (f"{GRAPH}/oauth/access_token?client_id={urllib.parse.quote(client_id)}"
           f"&redirect_uri={urllib.parse.quote(REDIRECT, safe='')}"
           f"&client_secret={{g}}&code={urllib.parse.quote(code, safe='')}")
    status, body = vault_do("GET", url)
    try:
        d = json.loads(body)
    except ValueError:
        d = {}
    if status >= 400 or "access_token" not in d:
        fail("the code could not be exchanged: " + graph_error(body))
    short = d["access_token"]

    # 2. short-lived -> long-lived user token
    url = (f"{GRAPH}/oauth/access_token?grant_type=fb_exchange_token"
           f"&client_id={urllib.parse.quote(client_id)}"
           f"&client_secret={{g}}&fb_exchange_token={urllib.parse.quote(short, safe='')}")
    status, body = vault_do("GET", url)
    try:
        d = json.loads(body)
    except ValueError:
        d = {}
    long_token = d.get("access_token") or short

    # 3. find the Pages and their linked Instagram account
    accounts = graph("GET", "/me/accounts", token=long_token,
                     params={"fields": "id,name,access_token,instagram_business_account{id,username}",
                             "limit": 100})
    pages = accounts.get("data") if isinstance(accounts, dict) else None
    if not pages:
        fail("this Facebook account manages no Page. Create a Page first, then link again.")
    st["user_token"] = long_token
    st["pages"] = [{"id": p.get("id"), "name": p.get("name"),
                    "has_ig": bool(p.get("instagram_business_account"))} for p in pages]
    save_state(st)
    choose_page(st, long_token, pages, pages[0].get("id"))


def choose_page(st, user_token, pages, page_id):
    page = next((p for p in pages if p.get("id") == page_id), None)
    if page is None:
        ids = ", ".join(p.get("id", "?") for p in pages)
        fail(f"no Page with id {page_id}. Your Pages: {ids}")
    token = page.get("access_token")
    if not token:
        token = graph("GET", f"/{page_id}", token=user_token, params={"fields": "access_token"}).get("access_token")
    ig = page.get("instagram_business_account") or {}
    st.update({
        "page_id": page_id,
        "page_name": page.get("name") or page_id,
        "page_token": token,
        "ig_user_id": ig.get("id"),
        "ig_username": ig.get("username"),
        "linked_at": int(time.time()),
    })
    save_state(st)
    print(f"Connected to Page \"{st['page_name']}\" ({page_id}).")
    if ig.get("id"):
        print(f"Instagram: @{ig.get('username') or ig['id']} ({ig['id']}).")
    else:
        print("No Instagram account is linked to this Page. Instagram posting needs a Business or "
              "Creator account connected to a Facebook Page.")
    if len(pages) > 1:
        print("More Pages? Switch with: socials koppel --pagina <page-id>")


def select_page(page_id):
    st = load_state()
    token = st.get("user_token")
    if not token:
        fail("not connected yet. Run `socials koppel <client-id>` first.")
    accounts = graph("GET", "/me/accounts", token=token,
                     params={"fields": "id,name,access_token,instagram_business_account{id,username}",
                             "limit": 100})
    choose_page(st, token, accounts.get("data") or [], page_id)


# ---------------------------------------------------------------- drafts

def new_draft(target, text, image=None):
    st = load_state()
    did = secrets.token_hex(3)
    st.setdefault("pending", {})[did] = {"target": target, "text": text,
                                         "image": image, "ts": int(time.time())}
    save_state(st)
    return did


def take_draft(did):
    st = load_state()
    d = (st.get("pending") or {}).get(did)
    if not d:
        fail(f"no draft {did}. Make one first, e.g. socials facebook post \"...\"")
    if int(time.time()) - int(d.get("ts", 0)) > DRAFT_TTL:
        st["pending"].pop(did, None)
        save_state(st)
        fail(f"draft {did} is more than an hour old; make a fresh one.")
    st["pending"].pop(did, None)
    save_state(st)
    return d


def ask(target, text, image, extra=""):
    did = new_draft(target, text, image)
    print(f"DRAFT {did} - nothing has been published.")
    print()
    print(text)
    if image:
        print(f"\n[image] {image}")
    if extra:
        print(extra)
    print()
    print("Show this on screen and only continue after the owner says yes:")
    print(f"  socials {target} post --ja {did}")
    return did


# ---------------------------------------------------------------- commands

def status():
    st = load_state()
    client_id = st.get("client_id")
    print("Socials: Facebook Page and Instagram, through your own Meta app.")
    print()
    if not client_id:
        print("Not set up yet. You need:")
        print("  1. a Meta app with Facebook Login for Business (developers.facebook.com)")
        print(f"  2. the redirect {REDIRECT} added to the app's Valid OAuth Redirect URIs")
        print("  3. a Facebook Page, and for Instagram a Business or Creator account linked to it")
        print()
        print("Then run: socials koppel <client-id>")
        return
    print(f"App client id: {client_id}")
    print(f"App secret: {'in the vault' if vault_has(VAULT_ITEM) else 'MISSING (kluis vraag socials-meta --domein facebook.com)'}")
    if not st.get("page_token"):
        print("Not connected. Run: socials koppel " + client_id)
        return
    print(f"Facebook Page: {st.get('page_name')} ({st.get('page_id')})")
    if st.get("ig_user_id"):
        print(f"Instagram: @{st.get('ig_username') or st['ig_user_id']} ({st['ig_user_id']})")
    else:
        print("Instagram: not linked. Instagram posting needs a Business or Creator account connected "
              "to a Facebook Page (that link is made in the Instagram app or Meta Business Suite).")
    print()
    print("Commands: socials facebook lijst|post, socials instagram lijst|post")


def facebook_list(rest):
    st = load_state()
    page_id, token = st.get("page_id"), st.get("page_token")
    if not page_id or not token:
        fail("not connected. Run `socials koppel <client-id>` first.")
    n = 10
    if "--max" in rest:
        try:
            n = max(1, min(100, int(rest[rest.index("--max") + 1])))
        except (ValueError, IndexError):
            fail("--max needs a number")
    d = graph("GET", f"/{page_id}/posts", token=token,
              params={"fields": "message,created_time,permalink_url", "limit": n})
    rows = d.get("data") or []
    if not rows:
        print("no posts on this Page yet")
        return
    for p in rows:
        when = (p.get("created_time") or "")[:16].replace("T", " ")
        text = (p.get("message") or "(no text)").replace("\n", " ")
        print(f"{when}  {text[:100]}")
        if p.get("permalink_url"):
            print(f"    {p['permalink_url']}")


def facebook_post(rest):
    if "--ja" in rest:
        i = rest.index("--ja")
        did = rest[i + 1] if i + 1 < len(rest) else None
        if not did:
            fail("use: socials facebook post --ja <draft-id>")
        d = take_draft(did)
        if d.get("target") != "facebook":
            fail(f"draft {did} is not a Facebook draft")
        st = load_state()
        r = graph("POST", f"/{st['page_id']}/feed", token=st["page_token"],
                  params={"message": d["text"]})
        pid = r.get("id", "?")
        print(f"published to Facebook: https://www.facebook.com/{pid}")
        return
    st = load_state()
    if not st.get("page_id") or not st.get("page_token"):
        fail("not connected. Run `socials koppel <client-id>` first.")
    text = " ".join(rest).strip()
    if not text:
        fail('use: socials facebook post "<text>"')
    ask("facebook", text, None)


def instagram_list(rest):
    st = load_state()
    ig, token = st.get("ig_user_id"), st.get("page_token")
    if not ig:
        fail("Instagram is not linked. It needs a Business or Creator account connected to a Facebook "
             "Page; link it in the Instagram app or Meta Business Suite, then run `socials koppel` again.")
    n = 10
    if "--max" in rest:
        try:
            n = max(1, min(100, int(rest[rest.index("--max") + 1])))
        except (ValueError, IndexError):
            fail("--max needs a number")
    d = graph("GET", f"/{ig}/media", token=token,
              params={"fields": "caption,media_type,permalink,timestamp", "limit": n})
    rows = d.get("data") or []
    if not rows:
        print("no media on this Instagram account yet")
        return
    for p in rows:
        when = (p.get("timestamp") or "")[:16].replace("T", " ")
        text = (p.get("caption") or "(no caption)").replace("\n", " ")
        print(f"{when}  [{p.get('media_type', '?')}]  {text[:100]}")
        if p.get("permalink"):
            print(f"    {p['permalink']}")


def instagram_post(rest):
    if "--ja" in rest:
        i = rest.index("--ja")
        did = rest[i + 1] if i + 1 < len(rest) else None
        if not did:
            fail("use: socials instagram post --ja <draft-id>")
        d = take_draft(did)
        if d.get("target") != "instagram":
            fail(f"draft {did} is not an Instagram draft")
        st = load_state()
        if not st.get("ig_user_id"):
            fail("Instagram is not linked. It needs a Business or Creator account connected to a Facebook Page.")
        if not d.get("image"):
            fail("Instagram needs a public image URL (--beeld URL); text-only posts are not supported.")
        container = graph("POST", f"/{st['ig_user_id']}/media", token=st["page_token"],
                          params={"image_url": d["image"], "caption": d["text"]})
        cid = container.get("id")
        if not cid:
            fail("Instagram did not return a container id")
        published = graph("POST", f"/{st['ig_user_id']}/media_publish", token=st["page_token"],
                          params={"creation_id": cid})
        mid = published.get("id", "?")
        link = ""
        try:
            info = graph("GET", f"/{mid}", token=st["page_token"], params={"fields": "permalink"})
            link = info.get("permalink") or ""
        except RuntimeError:
            pass
        print(f"published to Instagram: {link or mid}")
        return
    image = None
    if "--beeld" in rest:
        i = rest.index("--beeld")
        if i + 1 >= len(rest):
            fail("--beeld needs a URL")
        image = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    text = " ".join(rest).strip()
    if not text:
        fail('use: socials instagram post "<caption>" [--beeld URL]')
    st = load_state()
    if not st.get("ig_user_id"):
        fail("Instagram is not linked. It needs a Business or Creator account connected to a Facebook Page.")
    if not image:
        fail("Instagram needs a public image URL: --beeld https://...")
    ask("instagram", text, image)


def main():
    a = sys.argv[1:]
    if not a:
        status()
        return
    if a[0] == "facebook" and len(a) >= 2 and a[1] == "lijst":
        facebook_list(a[2:])
    elif a[0] == "facebook" and len(a) >= 2 and a[1] == "post":
        facebook_post(a[2:])
    elif a[0] == "instagram" and len(a) >= 2 and a[1] == "lijst":
        instagram_list(a[2:])
    elif a[0] == "instagram" and len(a) >= 2 and a[1] == "post":
        instagram_post(a[2:])
    elif a[0] == "koppel":
        rest = a[1:]
        if "--code" in rest:
            i = rest.index("--code")
            if i + 1 >= len(rest):
                fail('use: socials koppel --code "<code or redirected URL>"')
            finish_link(rest[i + 1])
        elif "--pagina" in rest:
            i = rest.index("--pagina")
            if i + 1 >= len(rest):
                fail("use: socials koppel --pagina <page-id>")
            select_page(rest[i + 1])
        elif rest and not rest[0].startswith("--"):
            start_link(rest[0])
        else:
            st = load_state()
            if st.get("client_id"):
                start_link(st["client_id"])
            else:
                print("Give your Meta app client id: socials koppel <client-id>\n"
                      "Create the app at developers.facebook.com (Facebook Login for Business) and add "
                      f"the redirect {REDIRECT}.")
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        fail(str(e))
    except KeyboardInterrupt:
        print("\nsocials: stopped")
        sys.exit(1)
