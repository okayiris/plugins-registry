#!/usr/bin/env python3
"""OpenRouter for Iris: use your own OpenRouter account and key for text, images and video,
paid from your own credit, outside the Iris credit.

  openrouter                          what is set up, and the default models
  openrouter models [search]          the models OpenRouter offers (public, no key needed)
  openrouter models --all             every text model, up to a limit
  openrouter ask "<question>" [--model ID] [--system "..."]

  openrouter image "<prompt>" [--model ID] [--out NAME]
                                      draw an image and save it in ~/inbox
  openrouter video "<prompt>" [--model ID]
                                      a clip, only when OpenRouter has a video model
  openrouter setup                    paste the API key into the vault, once
  openrouter key                      is the key there, and under which vault name
  openrouter key item <name> [--domain D]
                                      use another vault item for the key
  openrouter default [ask|image|video] [model]
                                      show or set a default model in config.json

The key lives in the vault; this tool never sees it and never prints it. Nothing is stored in this
folder except config.json. Every command here is an explicit order from you and is paid from your own
OpenRouter credit, so nothing runs by itself. The model list is public and needs no key.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
INBOX = os.path.expanduser("~/inbox")
API = "https://openrouter.ai/api/v1"
DEFAULT_ITEM = "openrouter-api"
DEFAULT_DOMAIN = "openrouter.ai"
FALLBACK_DEFAULTS = {
    "ask": "google/gemini-3.8-flash",
    "image": "google/gemini-3.1-flash-image",
    "video": "",
}
MEDIA_EXT = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "webp": "webp", "gif": "gif", "mp4": "mp4", "webm": "webm"}


def fail(text):
    print("openrouter: " + text)
    sys.exit(1)


# ---------------------------------------------------------------- config

def load_config():
    cfg = {
        "defaults": dict(FALLBACK_DEFAULTS),
        "vault_item": DEFAULT_ITEM,
        "vault_domain": DEFAULT_DOMAIN,
    }
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return cfg
    if not isinstance(raw, dict):
        return cfg
    d = raw.get("defaults")
    if isinstance(d, dict):
        for k in ("ask", "image", "video"):
            if isinstance(d.get(k), str):
                cfg["defaults"][k] = d[k].strip()
    if isinstance(raw.get("vault_item"), str) and raw["vault_item"].strip():
        cfg["vault_item"] = raw["vault_item"].strip()
    if isinstance(raw.get("vault_domain"), str) and raw["vault_domain"].strip():
        cfg["vault_domain"] = raw["vault_domain"].strip()
    return cfg


def save_config(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, CONFIG_PATH)


# ---------------------------------------------------------------- the vault

def vault_bin():
    p = shutil.which("kluis") or shutil.which("vault")
    if p:
        return p
    p = os.path.expanduser("~/.local/bin/kluis")
    return p if os.path.isfile(p) else None


def vault_items():
    exe = vault_bin()
    if not exe:
        return []
    try:
        proc = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    out = (proc.stdout or "").strip()
    if not out or "leeg" in out.lower() or "empty" in out.lower():
        return []
    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        names.append(re.split(r"\s{2,}", line)[0].strip())
    return names


def have_key(cfg):
    return cfg["vault_item"] in vault_items()


def ask_key(cfg):
    """Let the owner paste the key in the vault window; the value never comes here."""
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system")
    print("The vault opens a window on your Mac to paste the OpenRouter key; it goes straight into the vault.")
    print("This tool never sees it. Every call after this is paid from your own OpenRouter credit.")
    try:
        proc = subprocess.run(
            [exe, "vraag", cfg["vault_item"], "--domein", cfg["vault_domain"],
             "OpenRouter API key, for text, images and video on your own account"],
            capture_output=True, text=True, timeout=200)
    except subprocess.TimeoutExpired:
        fail("the vault did not get an answer in time; nothing was saved")
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        fail(err or out or "the vault did not save a key")
    print(out or f'saved as "{cfg["vault_item"]}" in the vault.')


def ensure_key(cfg):
    if have_key(cfg):
        return
    print("No OpenRouter key in the vault yet." if vault_bin() else "The vault is not available here.")
    ask_key(cfg)


def vault_call(cfg, method, url, body=None):
    """Let the vault make the call, so the key never enters this process. Returns (status, text)."""
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system")
    cmd = [exe, "doe", cfg["vault_item"], method, url]
    if body is not None:
        cmd.append(body)
    cmd += ["--kop", "Authorization: Bearer {g}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        fail("OpenRouter did not answer in time")
    out = (proc.stdout or "").strip()
    first, _, rest = out.partition("\n")
    if first.startswith("status "):
        try:
            return int(first.split()[1]), rest.strip()
        except (IndexError, ValueError):
            pass
    msg = (proc.stderr or out).strip() or "the vault refused the call"
    for pre in ("kluis:", "vault:"):
        if msg.startswith(pre):
            msg = msg[len(pre):].strip()
    fail(msg)


# ---------------------------------------------------------------- OpenRouter

def openrouter_error(status, text):
    msg = ""
    try:
        d = json.loads(text)
        e = d.get("error") if isinstance(d, dict) else None
        if isinstance(e, dict):
            msg = e.get("message") or ""
        elif isinstance(e, str):
            msg = e
        if not msg and isinstance(d, dict):
            msg = d.get("message") or ""
    except (ValueError, AttributeError):
        msg = (text or "")[:200]
    if status == 401:
        return ("OpenRouter refused the key (401). It is wrong or revoked; put a fresh one in the vault "
                "with `openrouter setup`.")
    if status == 402:
        return ("OpenRouter says your credit is too low (402). Top up at https://openrouter.ai/credits.")
    if status == 404:
        return (f"OpenRouter does not know that model (404): {msg or 'unknown model'}. "
                "Find one with `openrouter models <search>`.")
    if status == 429:
        return "OpenRouter's rate limit is reached (429). Try again shortly."
    return f"OpenRouter returned {status}: {msg or 'unknown error'}"


def fetch_models():
    """The public model list; no key and no credit needed."""
    req = urllib.request.Request(API + "/models", headers={"Accept": "application/json",
                                                           "User-Agent": "Iris-openrouter/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        fail(f"cannot reach OpenRouter's model list ({e.code})")
    except (OSError, ValueError) as e:
        fail(f"cannot reach OpenRouter's model list ({e})")
    return d.get("data") if isinstance(d, dict) else None


def call_json(cfg, path, body):
    ensure_key(cfg)
    status, text = vault_call(cfg, "POST", API + path, json.dumps(body))
    if status >= 400:
        fail(openrouter_error(status, text))
    try:
        return json.loads(text) if text else None
    except ValueError:
        fail("OpenRouter did not return JSON")


def footer(model, usage):
    parts = [model]
    if isinstance(usage, dict):
        tokens = usage.get("total_tokens")
        if isinstance(tokens, int):
            parts.append(f"{tokens} tokens")
        cost = usage.get("cost", usage.get("total_cost"))
        try:
            if cost is not None:
                parts.append(f"${float(cost):.4f}")
        except (TypeError, ValueError):
            pass
    return "  |  ".join(parts)


def message_of(d):
    try:
        return (d.get("choices") or [{}])[0].get("message") or {}
    except (AttributeError, IndexError):
        return {}


def media_url_of(x):
    if isinstance(x, str):
        return x if x.startswith(("data:", "http")) else None
    if not isinstance(x, dict):
        return None
    for key in ("image_url", "video_url", "url", "data"):
        v = x.get(key)
        if isinstance(v, dict) and isinstance(v.get("url"), str):
            return v["url"]
        if isinstance(v, str) and v.startswith(("data:", "http")):
            return v
    return None


def find_media(msg, kind):
    """The first image or video in a reply, in any of the shapes providers use."""
    for key in (kind + "s", "media"):
        items = msg.get(key)
        if isinstance(items, list):
            for item in items:
                url = media_url_of(item)
                if url:
                    return url
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") and kind not in str(part.get("type")):
                continue
            url = media_url_of(part)
            if url:
                return url
    return None


def text_of(msg):
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) for p in content
                        if isinstance(p, dict) and p.get("text")).strip()
    return ""


def safe_name(name, ext):
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name)).strip("-") or "openrouter"
    if not base.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm")):
        base += "." + ext
    return base


def save_media(url, kind, name=None):
    if url.startswith("data:"):
        m = re.match(r"^data:([a-z0-9.+-]+/[a-z0-9.+-]+);base64,(.*)$", url, re.S | re.I)
        if not m:
            fail("OpenRouter returned media this tool does not understand")
        mime, b64 = m.group(1), m.group(2)
        try:
            data = base64.b64decode(b64)
        except (ValueError, TypeError):
            fail("OpenRouter returned media this tool could not decode")
        ext = MEDIA_EXT.get(mime.split("/")[1].lower(), "png")
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "Iris-openrouter/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
                mime = (r.headers.get("Content-Type") or "").split(";")[0]
        except urllib.error.HTTPError as e:
            fail(f"could not download the {kind} ({e.code})")
        except OSError as e:
            fail(f"could not download the {kind} ({e})")
        ext = MEDIA_EXT.get(mime.split("/")[1].lower(), "png" if kind == "image" else "mp4")
    os.makedirs(INBOX, exist_ok=True)
    if name:
        path = os.path.join(INBOX, safe_name(name, ext))
    else:
        path = os.path.join(INBOX, time.strftime("openrouter-%Y%m%d-%H%M%S") + "." + ext)
    stem, suffix = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{stem}-{n}{suffix}"
        n += 1
    with open(path, "wb") as f:
        f.write(data)
    return path


# ---------------------------------------------------------------- commands

def status(cfg):
    print("OpenRouter: your own account and key for text, images and video.")
    print()
    if vault_bin() and have_key(cfg):
        print(f'Key: in the vault as "{cfg["vault_item"]}" (this tool never sees it).')
    else:
        print("Key: not set yet. Run `openrouter setup` to paste it into the vault.")
    print(f'Model for text:   {cfg["defaults"]["ask"]}')
    print(f'Model for images: {cfg["defaults"]["image"]}')
    print(f'Model for video:  {cfg["defaults"]["video"] or "none yet"}')
    print()
    print("Every call is an explicit command and is paid from your own OpenRouter credit.")
    print('Try: openrouter models gemini  |  openrouter ask "..."  |  openrouter image "..."')


def models(pos, opts):
    search = " ".join(pos).strip().lower()
    data = fetch_models()
    if data is None:
        fail("OpenRouter did not return a model list")
    rows = []
    for m in data:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "")
        name = str(m.get("name") or "")
        arch = m.get("architecture") if isinstance(m.get("architecture"), dict) else {}
        outs = arch.get("output_modalities") or []
        if not isinstance(outs, list):
            outs = []
        if search:
            if search not in mid.lower() and search not in name.lower() and search not in " ".join(map(str, outs)):
                continue
        elif not opts.get("all") and "text" not in outs:
            continue
        rows.append((mid, name, outs))
    rows.sort()
    shown = rows[:100]
    for mid, name, outs in shown:
        tag = " [image]" if "image" in outs else (" [video]" if "video" in outs else "")
        print(f"{mid}  {name}{tag}")
    if not shown:
        print(f'no model matches "{search}"' if search else "no models found")
        return
    if len(rows) > len(shown):
        print(f"... and {len(rows) - len(shown)} more; add a search term to narrow it down.")
    if search:
        print(f"{len(rows)} match on OpenRouter ({len(data)} models in total).")
    else:
        print(f"{len(rows)} text models on OpenRouter ({len(data)} in total). "
              "Add a search term, or `openrouter models <term>` for image models.")


def ask(pos, opts, cfg):
    prompt = " ".join(pos).strip()
    if not prompt:
        fail('use: openrouter ask "<question>" [--model <id>] [--system "..."]')
    model = opts.get("model") or cfg["defaults"]["ask"]
    messages = []
    if opts.get("system"):
        messages.append({"role": "system", "content": opts["system"]})
    messages.append({"role": "user", "content": prompt})
    d = call_json(cfg, "/chat/completions", {"model": model, "messages": messages})
    msg = message_of(d)
    answer = text_of(msg) or text_of({"content": msg.get("reasoning")})
    print(answer or "(OpenRouter gave an empty answer)")
    print()
    print(footer(model, (d or {}).get("usage")))


def image(pos, opts, cfg):
    prompt = " ".join(pos).strip()
    if not prompt:
        fail('use: openrouter image "<prompt>" [--model <id>] [--out NAME]')
    model = opts.get("model") or cfg["defaults"]["image"]
    d = call_json(cfg, "/chat/completions",
                  {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "modalities": ["image", "text"]})
    msg = message_of(d)
    url = find_media(msg, "image")
    answer = text_of(msg)
    if not url:
        if answer:
            print(answer)
        fail("OpenRouter returned no image. Use an image model, e.g. `openrouter models image`.")
    path = save_media(url, "image", opts.get("out"))
    if answer:
        print(answer)
    print(f"saved to {path}")
    print(footer(model, (d or {}).get("usage")))


def video(pos, opts, cfg):
    prompt = " ".join(pos).strip()
    if not prompt:
        fail('use: openrouter video "<prompt>" [--model <id>]')
    model = opts.get("model") or cfg["defaults"]["video"]
    if not model:
        data = fetch_models() or []
        clips = []
        for m in data:
            arch = m.get("architecture") if isinstance(m, dict) and isinstance(m.get("architecture"), dict) else {}
            if "video" in (arch.get("output_modalities") or []):
                clips.append(m.get("id"))
        if not clips:
            print("OpenRouter does not offer video generation right now: none of its models returns video.")
            print("Only a model that outputs video can make a clip; `openrouter models` shows what is there.")
            print("As soon as one appears, `openrouter video` can use it (or point --model at it yourself).")
            return
        model = sorted(clips)[0]
    d = call_json(cfg, "/chat/completions",
                  {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "modalities": ["video", "text"]})
    msg = message_of(d)
    url = find_media(msg, "video")
    answer = text_of(msg)
    if not url:
        if answer:
            print(answer)
        fail(f"{model} returned no video.")
    path = save_media(url, "video", opts.get("out"))
    if answer:
        print(answer)
    print(f"saved to {path}")
    print(footer(model, (d or {}).get("usage")))


def setup(cfg):
    if have_key(cfg):
        print(f'A key is already in the vault as "{cfg["vault_item"]}".')
        print("The vault opens a window again to replace it; cancel to keep the current one.")
    ask_key(cfg)


def key(pos, opts, cfg):
    if not pos or pos[0] == "show":
        if have_key(cfg):
            print(f'a key is in the vault as "{cfg["vault_item"]}" (never shown).')
        else:
            print(f'no key yet (looked for "{cfg["vault_item"]}"). Run `openrouter setup`.')
        return
    if pos[0] == "item":
        name = opts.get("name") or (pos[1] if len(pos) > 1 else "")
        if not name:
            fail("openrouter key item <name> [--domain <domain>]")
        cfg["vault_item"] = name
        if opts.get("domain"):
            cfg["vault_domain"] = opts["domain"]
        save_config(cfg)
        print(f'using vault item "{name}" for {cfg["vault_domain"]}')
        return
    fail("openrouter key [item <name> [--domain D]]")


def default(pos, opts, cfg):
    names = {"ask": "ask", "image": "image", "video": "video"}
    if not pos:
        print(f'text:   {cfg["defaults"]["ask"]}')
        print(f'image:  {cfg["defaults"]["image"]}')
        print(f'video:  {cfg["defaults"]["video"] or "none yet"}')
        print("Set one with: openrouter default image <model-id>")
        return
    which = names.get(pos[0])
    if not which:
        fail("openrouter default [ask|image|video] [model]")
    if len(pos) > 1:
        cfg["defaults"][which] = " ".join(pos[1:]).strip()
        save_config(cfg)
        print(f'default for {which}: {cfg["defaults"][which] or "none yet"}')
    else:
        print(cfg["defaults"][which] or "none yet")


# ---------------------------------------------------------------- parser

def parse(args, valued=(), flags=()):
    pos = []
    opts = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            k = a[2:]
            if k in valued:
                if i + 1 >= len(args):
                    fail(f"{a} needs a value")
                opts[k] = args[i + 1]
                i += 2
            elif k in flags:
                opts[k] = True
                i += 1
            else:
                fail(f"unknown option {a}")
        else:
            pos.append(a)
            i += 1
    return pos, opts


def main():
    cfg = load_config()
    a = sys.argv[1:]
    if not a:
        status(cfg)
        return
    cmd, rest = a[0], a[1:]
    if cmd in ("help", "--help", "-h"):
        print(__doc__.strip())
    elif cmd == "models":
        pos, opts = parse(rest, flags=("all",))
        models(pos, opts)
    elif cmd == "ask":
        pos, opts = parse(rest, valued=("model", "system"))
        ask(pos, opts, cfg)
    elif cmd == "image":
        pos, opts = parse(rest, valued=("model", "out"))
        image(pos, opts, cfg)
    elif cmd == "video":
        pos, opts = parse(rest, valued=("model", "out"))
        video(pos, opts, cfg)
    elif cmd == "setup":
        setup(cfg)
    elif cmd == "key":
        pos, opts = parse(rest, valued=("name", "domain"))
        key(pos, opts, cfg)
    elif cmd == "default":
        pos, opts = parse(rest)
        default(pos, opts, cfg)
    else:
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nopenrouter: stopped")
        sys.exit(1)
