#!/usr/bin/env python3
"""Home Assistant for Iris: read and steer the smart devices in the house.

  home                       is Home Assistant reachable, and how many entities it has
  home staten [filter]       the states, optionally only those whose name or id contains <filter>
  home aan <entity>          turn an entity on
  home uit <entity>          turn an entity off
  home zet <entity> <value>  set a value: on/off, a percentage for a light, a temperature for a
                             thermostat, a volume for a speaker, an option for a dropdown

The base URL goes in config.json next to this file (not a secret):

  {"url": "http://homeassistant.local:8123"}

The long-lived access token goes in the vault, never here:

  kluis vraag homeassistant --domein homeassistant.local:8123 "Langlevend toegangstoken van Home Assistant"

The token never reaches this script: every call is made by the vault itself, and only the answer comes back.
Use the entity_id (light.keuken) or a friendly name (Keukenlamp); a friendly name is looked up for you.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS = HERE / "config.json"
VAULT = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN") or "kluis"


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(data):
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def norm_domain(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    value = value.split("/")[0]
    return value


def bare_host(value):
    host = norm_domain(value)
    return host.split(":")[0]


def vault_items():
    try:
        proc = subprocess.run([VAULT, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    items = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        parts = [p for p in re.split(r"\s{2,}", line) if p]
        if len(parts) >= 3:
            items.append({"name": parts[0], "user": parts[1], "domain": parts[2]})
    return items


def find_item(url):
    """Find a vault item whose domain belongs to this Home Assistant address."""
    host = norm_domain(url)
    short = bare_host(url)
    for item in vault_items():
        dom = norm_domain(item["domain"])
        if dom == host or bare_host(dom) == short:
            return item["name"]
    return None


def vault_call(item, method, url, body=None, header=None, timeout=90):
    """Let the vault make the call, so the token never enters this process. Returns (status, body)."""
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


def base_url(settings):
    url = (settings.get("url") or "").strip().rstrip("/")
    if url and not re.match(r"^[a-z]+://", url):
        url = "http://" + url
    return url


def explain_missing(settings):
    url = base_url(settings)
    print("Home Assistant is nog niet gekoppeld.")
    if not url:
        print('Zet je adres in config.json naast deze plugin: {"url": "http://homeassistant.local:8123"}.')
        print("Dat adres is niet geheim, dus het mag daar staan.")
    else:
        host = bare_host(url)
        print(f"Je adres staat op {url}, maar de kluis heeft nog geen token voor dat adres.")
        print(f'Vraag hem zo: kluis vraag homeassistant --domein {host} "Langlevend toegangstoken van Home Assistant"')
    print("Een langlevend toegangstoken maak je in Home Assistant onder je profiel, helemaal onderaan.")


def get(url, path, item):
    return vault_call(item, "GET", url + path, header="Authorization: Bearer {g}")


def post(url, path, item, payload):
    body = json.dumps(payload, ensure_ascii=False)
    return vault_call(item, "POST", url + path, body=body, header="Authorization: Bearer {g}")


def need_connection(settings):
    url = base_url(settings)
    if not url:
        return None, None, None
    item = find_item(url)
    if not item:
        return url, None, None
    return url, item, None


def parse_json(status, body):
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return None


def states(url, item):
    status, body = get(url, "/api/states", item)
    if status is None:
        return None, body
    data = parse_json(status, body)
    if status != 200 or data is None:
        return None, friendly_error(status, body)
    return data, None


def friendly_error(status, body):
    data = parse_json(status, body)
    if isinstance(data, dict) and data.get("message"):
        return f"Home Assistant antwoordde: {data['message']}"
    if status == 401:
        return "Het toegangstoken werd geweigerd. Maak een nieuw token en vraag het opnieuw."
    if status == 404:
        return "Home Assistant kent dat adres of die entiteit niet."
    return f"Home Assistant antwoordde met status {status}."


def resolve_entity(url, item, wanted):
    """Turn a friendly name into an entity_id when needed."""
    data, err = states(url, item)
    if err:
        return None, err
    wanted_low = wanted.strip().lower()
    for state in data:
        if state.get("entity_id", "").lower() == wanted_low:
            return state["entity_id"], None
    for state in data:
        name = str(state.get("attributes", {}).get("friendly_name", "")).lower()
        if name == wanted_low:
            return state["entity_id"], None
    matches = [s["entity_id"] for s in data
               if wanted_low in s.get("entity_id", "").lower()
               or wanted_low in str(s.get("attributes", {}).get("friendly_name", "")).lower()]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"Ik zie geen entiteit die op '{wanted}' lijkt."
    return None, "Meerdere entiteiten passen: " + ", ".join(matches[:8]) + ". Noem de entity_id."


def display_name(state):
    return state.get("attributes", {}).get("friendly_name") or state.get("entity_id")


def cmd_status(settings):
    url = base_url(settings)
    item = find_item(url) if url else None
    if not url or not item:
        explain_missing(settings)
        return
    data, err = states(url, item)
    if err:
        print(err)
        return
    on = sum(1 for s in data if str(s.get("state")) in ("on", "open", "home", "playing"))
    print(f"Home Assistant is bereikbaar op {url}: {len(data)} entiteiten, {on} actief.")
    lights = [s for s in data if s.get("entity_id", "").startswith("light.")]
    if lights:
        on_lights = [display_name(s) for s in lights if s.get("state") == "on"]
        print(f"Lichten: {len(on_lights)} aan" + (": " + ", ".join(on_lights[:6]) if on_lights else "") + ".")


def cmd_states(settings, flt):
    url = base_url(settings)
    item = find_item(url) if url else None
    if not url or not item:
        explain_missing(settings)
        return
    data, err = states(url, item)
    if err:
        print(err)
        return
    if flt:
        low = flt.lower()
        data = [s for s in data
                if low in s.get("entity_id", "").lower()
                or low in str(s.get("attributes", {}).get("friendly_name", "")).lower()]
    if not data:
        print("Niets gevonden." if flt else "Home Assistant heeft geen entiteiten.")
        return
    for state in data[:60]:
        unit = state.get("attributes", {}).get("unit_of_measurement", "")
        print(f"{display_name(state)}: {state.get('state')}{(' ' + unit) if unit else ''}  ({state.get('entity_id')})")
    if len(data) > 60:
        print(f"... en nog {len(data) - 60}.")


def cmd_aanuit(settings, entity, on):
    url = base_url(settings)
    item = find_item(url) if url else None
    if not url or not item:
        explain_missing(settings)
        return
    resolved, err = resolve_entity(url, item, entity)
    if err:
        print(err)
        return
    service = "turn_on" if on else "turn_off"
    status, body = post(url, f"/api/services/homeassistant/{service}", item, {"entity_id": resolved})
    if status is None:
        print(body)
        return
    if status >= 400:
        print(friendly_error(status, body))
        return
    print(f"{resolved} is {'aan' if on else 'uit'}.")


def service_for(entity_id, value):
    domain = entity_id.split(".", 1)[0]
    low = value.strip().lower()
    if low in ("aan", "on", "open"):
        return "homeassistant", "turn_on", {"entity_id": entity_id}
    if low in ("uit", "off", "dicht", "close"):
        return "homeassistant", "turn_off", {"entity_id": entity_id}
    if domain == "light":
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            return "homeassistant", "turn_on", {"entity_id": entity_id}
        pct = number if number <= 100 else min(100, round(number / 255 * 100))
        return "light", "turn_on", {"entity_id": entity_id, "brightness_pct": pct}
    if domain == "climate":
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            return "homeassistant", "turn_on", {"entity_id": entity_id}
        return "climate", "set_temperature", {"entity_id": entity_id, "temperature": number}
    if domain == "media_player":
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            return "homeassistant", "turn_on", {"entity_id": entity_id}
        volume = number if number <= 1 else number / 100
        return "media_player", "volume_set", {"entity_id": entity_id, "volume_level": volume}
    if domain == "cover":
        try:
            number = int(float(value.replace(",", ".")))
        except ValueError:
            return "homeassistant", "turn_on", {"entity_id": entity_id}
        return "cover", "set_cover_position", {"entity_id": entity_id, "position": number}
    if domain in ("input_number", "number"):
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            return "homeassistant", "turn_on", {"entity_id": entity_id}
        return domain, "set_value", {"entity_id": entity_id, "value": number}
    if domain in ("input_select", "select"):
        return domain, "select_option", {"entity_id": entity_id, "option": value}
    if domain in ("input_text", "text"):
        return domain, "set_value", {"entity_id": entity_id, "value": value}
    if domain == "fan":
        try:
            number = int(float(value.replace(",", ".")))
        except ValueError:
            return "homeassistant", "turn_on", {"entity_id": entity_id}
        return "fan", "set_percentage", {"entity_id": entity_id, "percentage": number}
    return "homeassistant", "turn_on", {"entity_id": entity_id}


def cmd_zet(settings, entity, value):
    url = base_url(settings)
    item = find_item(url) if url else None
    if not url or not item:
        explain_missing(settings)
        return
    resolved, err = resolve_entity(url, item, entity)
    if err:
        print(err)
        return
    domain, service, payload = service_for(resolved, value)
    status, body = post(url, f"/api/services/{domain}/{service}", item, payload)
    if status is None:
        print(body)
        return
    if status >= 400:
        print(friendly_error(status, body))
        return
    print(f"{resolved} staat op {value}.")


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return
    settings = load_settings()
    if not args or args[0] == "status":
        cmd_status(settings)
    elif args[0] == "staten":
        cmd_states(settings, " ".join(args[1:]) if len(args) > 1 else "")
    elif args[0] in ("aan", "uit"):
        if len(args) != 2:
            print(__doc__.strip())
            return
        cmd_aanuit(settings, args[1], args[0] == "aan")
    elif args[0] == "zet":
        if len(args) < 3:
            print(__doc__.strip())
            return
        cmd_zet(settings, args[1], " ".join(args[2:]))
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main()
