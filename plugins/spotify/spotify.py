#!/usr/bin/env python3
"""Spotify for Iris: see what is playing, search, and steer the player.

  spotify                 is Spotify linked, and what is playing right now
  spotify nu              the track that is playing
  spotify zoek "<text>"   search tracks and show their uri's
  spotify speel [uri]     resume, or play a track/album/playlist uri
  spotify pauze           pause
  spotify volgende        next track
  spotify vorige          previous track
  spotify login           print the one-time Spotify login link
  spotify login "<url>"   finish the login with the address you were sent to

Setup, once:

1. Make an app on https://developer.spotify.com/dashboard. Add this redirect URI to it:
     http://127.0.0.1:8888/callback
   Copy the app's Client ID and Client Secret.
2. Put the Client ID in config.json next to this file (not a secret), or pass it as the vault user:

   kluis vraag spotify --domein accounts.spotify.com --gebruiker <client-id> "Spotify client secret"

3. Run `spotify login`, open the link, approve, and run `spotify login "<the whole address you landed on>"`.

The client secret stays in the vault: the token exchange is done by the vault itself. Playing, pausing and
skipping need Spotify Premium and an active device (open Spotify on a phone, computer or speaker first).
"""
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS = HERE / "config.json"
TOKEN_FILE = HERE / ".token.json"
VAULT = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN") or "kluis"
TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
API = "https://api.spotify.com/v1"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"


def load_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def load_settings():
    return load_json(SETTINGS, {})


def load_tokens():
    return load_json(TOKEN_FILE, {})


def save_tokens(tokens):
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    try:
        TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def norm_domain(value):
    value = (value or "").strip().lower()
    value = urllib.parse.urlparse(value if "://" in value else "//" + value).hostname or value
    return value.split(":")[0].rstrip("/")


def vault_items():
    try:
        import subprocess
        proc = subprocess.run([VAULT, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    items = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        parts = [p for p in line.split("  ") if p.strip()]
        if len(parts) >= 3:
            items.append({"name": parts[0].strip(), "user": parts[1].strip(), "domain": parts[2].strip()})
    return items


def secret_item():
    for item in vault_items():
        if norm_domain(item["domain"]) == "accounts.spotify.com":
            return item
    return None


def vault_call(item, method, url, body=None, header=None, timeout=90):
    import subprocess
    cmd = [VAULT, "doe", item, method, url]
    if body is not None:
        cmd.append(body)
    if header:
        cmd += ["--kop", header]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, "de kluis is niet gevonden"
    except subprocess.TimeoutExpired:
        return None, "de kluis antwoordde niet op tijd"
    except OSError as exc:
        return None, str(exc)
    if not proc.stdout.strip():
        return None, (proc.stderr.strip() or "geen antwoord van de kluis")
    first, _, rest = proc.stdout.partition("\n")
    status = None
    if first.startswith("status "):
        try:
            status = int(first.split()[1])
        except (IndexError, ValueError):
            pass
    return status, rest


def form_body(pairs):
    parts = []
    for key, value in pairs:
        if value == "{g}":
            parts.append(f"{key}={{g}}")
        else:
            parts.append(f"{key}={urllib.parse.quote(str(value), safe='')}")
    return "&".join(parts)


def client_id(settings):
    if settings.get("client_id"):
        return settings["client_id"]
    item = secret_item()
    return item["user"] if item and item["user"] not in ("-", "") else ""


def explain_missing(settings):
    print("Spotify is nog niet gekoppeld.")
    if not client_id(settings):
        print("Zet je Client ID in config.json naast deze plugin, of vraag je geheim zo op:")
        print('  kluis vraag spotify --domein accounts.spotify.com --gebruiker <jouw-client-id> "Spotify client secret"')
    elif not secret_item():
        print("Je Client ID staat klaar, maar de kluis heeft nog geen client secret voor accounts.spotify.com:")
        print('  kluis vraag spotify --domein accounts.spotify.com --gebruiker <jouw-client-id> "Spotify client secret"')
    else:
        print("De app-gegevens staan klaar. Doe nog een keer inloggen:")
        print("  spotify login")
    print("Maak eerst een app op https://developer.spotify.com/dashboard met redirect http://127.0.0.1:8888/callback.")


def request_token(settings, pairs, cache_key):
    item = secret_item()
    if not item:
        return None, "geen client secret in de kluis"
    body = form_body(pairs)
    status, text = vault_call(item["name"], "POST", TOKEN_URL, body=body,
                              header="Content-Type: application/x-www-form-urlencoded")
    if status is None:
        return None, text
    data = None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        pass
    if status != 200 or not data or not data.get("access_token"):
        message = (data or {}).get("error_description") or (data or {}).get("error") or text
        return None, f"Spotify weigerde het token: {message}"
    return data, None


def current_user_token(settings):
    tokens = load_tokens()
    now = time.time()
    if tokens.get("access_token") and tokens.get("expires_at", 0) > now + 60:
        return tokens["access_token"], None
    if not tokens.get("refresh_token"):
        return None, "niet ingelogd"
    cid = client_id(settings)
    if not cid:
        return None, "geen client id"
    data, err = request_token(settings, [
        ("grant_type", "refresh_token"),
        ("refresh_token", tokens["refresh_token"]),
        ("client_id", cid),
        ("client_secret", "{g}"),
    ], "user")
    if err:
        return None, err
    tokens["access_token"] = data["access_token"]
    tokens["expires_at"] = now + int(data.get("expires_in", 3600))
    if data.get("refresh_token"):
        tokens["refresh_token"] = data["refresh_token"]
    save_tokens(tokens)
    return tokens["access_token"], None


def app_token(settings):
    tokens = load_tokens()
    now = time.time()
    if tokens.get("app_token") and tokens.get("app_expires_at", 0) > now + 60:
        return tokens["app_token"], None
    cid = client_id(settings)
    if not cid:
        return None, "geen client id"
    data, err = request_token(settings, [
        ("grant_type", "client_credentials"),
        ("client_id", cid),
        ("client_secret", "{g}"),
    ], "app")
    if err:
        return None, err
    tokens["app_token"] = data["access_token"]
    tokens["app_expires_at"] = now + int(data.get("expires_in", 3600))
    save_tokens(tokens)
    return tokens["app_token"], None


def api(method, path, token, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except (TypeError, ValueError):
            return exc.code, {"error": raw}
    except OSError as exc:
        return None, {"error": str(exc)}


def api_error(status, data):
    if status is None:
        return f"Spotify is niet bereikbaar ({data.get('error')})."
    if status == 403:
        return "Spotify weigert dit: het bedienen van de speler vraagt Spotify Premium."
    if status == 404:
        return "Geen actief apparaat. Open Spotify op een telefoon, computer of speaker en probeer opnieuw."
    if status == 401:
        return "De inlog is verlopen. Doe `spotify login` opnieuw."
    message = (data or {}).get("error", {})
    if isinstance(message, dict):
        message = message.get("message", "")
    return f"Spotify antwoordde met status {status}" + (f": {message}" if message else ".")


def track_line(item):
    if not item:
        return "Niets."
    name = item.get("name", "?")
    artists = ", ".join(a.get("name", "?") for a in item.get("artists", []))
    return f"{artists} - {name}" if artists else name


def playing(token):
    status, data = api("GET", "/me/player", token)
    if status == 204:
        return None, None
    if status is None or status >= 400:
        return None, api_error(status, data)
    return data, None


def cmd_status(settings):
    if not client_id(settings) or not secret_item():
        explain_missing(settings)
        return
    if not load_tokens().get("refresh_token"):
        print("Spotify-app staat klaar, maar je bent nog niet ingelogd.")
        print("Doe `spotify login` voor de eenmalige inlog. Zoeken werkt daarna al; de speler vraagt Premium.")
        return
    token, err = current_user_token(settings)
    if err:
        print(err if err != "niet ingelogd" else "Je bent nog niet ingelogd: doe `spotify login`.")
        return
    data, perr = playing(token)
    if perr:
        print(perr)
        return
    if not data or not data.get("item"):
        print("Spotify is gekoppeld, maar er speelt niets.")
        return
    where = data.get("device", {}).get("name", "?")
    state = "speelt" if data.get("is_playing") else "gepauzeerd"
    print(f"{track_line(data['item'])} ({state} op {where}).")


def cmd_nu(settings):
    if not client_id(settings) or not secret_item() or not load_tokens().get("refresh_token"):
        explain_missing(settings)
        return
    token, err = current_user_token(settings)
    if err:
        print(err)
        return
    data, perr = playing(token)
    if perr:
        print(perr)
        return
    if not data or not data.get("item"):
        print("Er speelt niets.")
        return
    item = data["item"]
    progress = int(data.get("progress_ms", 0)) // 1000
    length = int(item.get("duration_ms", 0)) // 1000
    where = data.get("device", {}).get("name", "?")
    print(f"{track_line(item)}  [{progress // 60}:{progress % 60:02d} / {length // 60}:{length % 60:02d}]  op {where}")
    print(item.get("external_urls", {}).get("spotify", ""))


def cmd_zoek(settings, query):
    if not client_id(settings) or not secret_item():
        explain_missing(settings)
        return
    token, err = app_token(settings)
    if err:
        print(err)
        return
    path = "/search?type=track&limit=5&q=" + urllib.parse.quote(query)
    status, data = api("GET", path, token)
    if status is None or status >= 400:
        print(api_error(status, data))
        return
    tracks = data.get("tracks", {}).get("items", [])
    if not tracks:
        print(f"Niets gevonden voor '{query}'.")
        return
    for track in tracks:
        print(f"{track_line(track)}  {track.get('uri')}")


def cmd_speel(settings, uri):
    if not client_id(settings) or not secret_item() or not load_tokens().get("refresh_token"):
        explain_missing(settings)
        return
    token, err = current_user_token(settings)
    if err:
        print(err)
        return
    body = {"uris": [uri]} if uri else None
    status, data = api("PUT", "/me/player/play", token, body)
    if status is None or status >= 400:
        print(api_error(status, data))
        return
    print("Speelt." + (f" {uri}" if uri else ""))


def cmd_simple(settings, method, path, done):
    if not client_id(settings) or not secret_item() or not load_tokens().get("refresh_token"):
        explain_missing(settings)
        return
    token, err = current_user_token(settings)
    if err:
        print(err)
        return
    status, data = api(method, path, token)
    if status is None or status >= 400:
        print(api_error(status, data))
        return
    print(done)


def cmd_login(settings, arg):
    cid = client_id(settings)
    if not cid:
        explain_missing(settings)
        return
    if not secret_item():
        explain_missing(settings)
        return
    redirect = settings.get("redirect_uri") or "http://127.0.0.1:8888/callback"
    if not arg:
        params = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": cid,
            "scope": SCOPES,
            "redirect_uri": redirect,
            "show_dialog": "false",
        })
        print("Open deze link, log in bij Spotify en geef toestemming:")
        print(f"{AUTHORIZE_URL}?{params}")
        print()
        print('Je komt uit op een adres dat niet laadt; dat maakt niet uit. Kopieer de hele adresbalk en doe:')
        print('  spotify login "<die hele adresbalk>"')
        return
    code = arg.strip()
    if "code=" in code:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    if not code:
        print("Ik zie geen code in die link. Kopieer de hele adresbalk waar Spotify je heen stuurde.")
        return
    data, err = request_token(settings, [
        ("grant_type", "authorization_code"),
        ("code", code),
        ("redirect_uri", redirect),
        ("client_id", cid),
        ("client_secret", "{g}"),
    ], "user")
    if err:
        print(err)
        return
    tokens = load_tokens()
    tokens.update({
        "access_token": data["access_token"],
        "expires_at": time.time() + int(data.get("expires_in", 3600)),
        "refresh_token": data.get("refresh_token", tokens.get("refresh_token", "")),
    })
    save_tokens(tokens)
    print("Gelukt, Spotify is ingelogd." + ("" if tokens.get("refresh_token") else " Geen refresh token ontvangen."))


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return
    settings = load_settings()
    if not args or args[0] == "status":
        cmd_status(settings)
    elif args[0] == "nu":
        cmd_nu(settings)
    elif args[0] == "zoek":
        if len(args) < 2:
            print('Gebruik: spotify zoek "<tekst>"')
            return
        cmd_zoek(settings, " ".join(args[1:]))
    elif args[0] == "speel":
        cmd_speel(settings, args[1] if len(args) > 1 else "")
    elif args[0] == "pauze":
        cmd_simple(settings, "PUT", "/me/player/pause", "Gepauzeerd.")
    elif args[0] == "volgende":
        cmd_simple(settings, "POST", "/me/player/next", "Volgende.")
    elif args[0] == "vorige":
        cmd_simple(settings, "POST", "/me/player/previous", "Vorige.")
    elif args[0] == "login":
        cmd_login(settings, args[1] if len(args) > 1 else "")
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main()
