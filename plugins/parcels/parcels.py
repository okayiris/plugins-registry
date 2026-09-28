#!/usr/bin/env python3
"""Track and trace for Iris: PostNL and DHL parcels.

  parcels                            all saved parcels with their latest status
  parcels add <code> [--vervoerder postnl|dhl]
                                    save a code (the carrier is guessed from the code)
  parcels verwijder <code>           forget a code
  parcels status <code>              the latest status of one code

Codes and carriers are not secret and live in config.json next to this file:

  {"parcels": [{"code": "3SBOL1234567890", "carrier": "postnl"}]}

The API keys go in the vault, one per carrier domain:

  kluis vraag pakketjes --domein api.postnl.nl "PostNL Track & Trace API key"
  kluis vraag pakketjes-dhl --domein api-eu.dhl.com "DHL Shipment Tracking API key"

The key never reaches this script: the call is made by the vault, with the key as {g} in the header.
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS = HERE / "config.json"
VAULT = os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN") or "kluis"

CARRIERS = {
    "postnl": {"label": "PostNL", "host": "api.postnl.nl"},
    "dhl": {"label": "DHL", "host": "api-eu.dhl.com"},
}


def load_settings():
    try:
        data = json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("parcels", [])
    return data


def save_settings(data):
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def norm_domain(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    return value.split("/")[0].split(":")[0]


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


def key_item(carrier):
    host = CARRIERS[carrier]["host"]
    short = host.split(".")[0]
    for item in vault_items():
        dom = norm_domain(item["domain"])
        if dom == host or dom.endswith("." + host) or dom == short or dom.endswith("." + host.split(".", 1)[1]):
            return item["name"]
    return None


def vault_call(item, method, url, header=None, timeout=60):
    cmd = [VAULT, "doe", item, method, url]
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


def guess_carrier(code):
    code_up = code.strip().upper()
    if re.match(r"^3S[A-Z0-9]{8,}", code_up):
        return "postnl"
    if code_up.startswith("JVGL") or code_up.startswith("GM") or re.match(r"^[0-9]{10,20}$", code_up):
        return "dhl"
    return None


def carrier_of(parcel):
    if parcel.get("carrier") in CARRIERS:
        return parcel["carrier"]
    return guess_carrier(parcel.get("code", ""))


def get_postnl(code, item):
    url = f"https://{CARRIERS['postnl']['host']}/shipment/v2/status/barcode/{urllib.parse.quote(code)}"
    status, text = vault_call(item, "GET", url, header="apikey: {g}")
    if status is None:
        return None, text
    data = parse_json(text)
    if data is None:
        return None, "PostNL gaf geen leesbaar antwoord."
    if status == 401:
        return None, "PostNL weigerde de sleutel."
    if status == 404:
        return None, "PostNL kent deze code niet."
    if status >= 400:
        warnings = data.get("Warnings") or []
        message = warnings[0].get("Message") if warnings and isinstance(warnings[0], dict) else None
        return None, message or f"PostNL antwoordde met status {status}."
    shipment = (data.get("CurrentStatus") or {}).get("Shipment") or {}
    complete = (data.get("CompleteStatus") or {}).get("Shipment") or {}
    result = {"code": code, "carrier": "postnl"}
    status_obj = shipment.get("Status") or {}
    result["state"] = status_obj.get("StatusDescription") or status_obj.get("PhaseDescription")
    result["moment"] = status_obj.get("TimeStamp")
    result["expected"] = shipment.get("DeliveryDate") or complete.get("DeliveryDate")
    events = complete.get("Event") or []
    if not result.get("state") and events:
        last = events[-1]
        result["state"] = last.get("Description")
        result["moment"] = last.get("TimeStamp")
    if not result.get("state"):
        warnings = data.get("Warnings") or []
        if warnings and isinstance(warnings[0], dict):
            result["state"] = warnings[0].get("Message")
    return result, None


def get_dhl(code, item):
    url = f"https://{CARRIERS['dhl']['host']}/track/shipments?trackingNumber={urllib.parse.quote(code)}"
    status, text = vault_call(item, "GET", url, header="DHL-API-Key: {g}")
    if status is None:
        return None, text
    data = parse_json(text)
    if data is None:
        return None, "DHL gaf geen leesbaar antwoord."
    if status == 401:
        return None, "DHL weigerde de sleutel."
    if status == 404:
        return None, "DHL kent deze code niet."
    if status >= 400:
        return None, f"DHL antwoordde met status {status}."
    shipments = data.get("shipments") or []
    if not shipments:
        return None, "DHL kent deze code niet."
    shipment = shipments[0]
    status_obj = shipment.get("status") or {}
    result = {"code": code, "carrier": "dhl"}
    result["state"] = status_obj.get("description") or status_obj.get("status") or status_obj.get("statusDetailed")
    result["moment"] = status_obj.get("timestamp")
    result["expected"] = (shipment.get("estimatedTimeOfDelivery")
                          or shipment.get("estimatedDeliveryTimeFrame", {}).get("estimatedFrom")
                          or shipment.get("agreedDeliveryDate"))
    events = shipment.get("events") or []
    if not result.get("state") and events:
        result["state"] = events[0].get("description")
        result["moment"] = events[0].get("timestamp")
    return result, None


def fetch(code, carrier):
    item = key_item(carrier)
    if not item:
        host = CARRIERS[carrier]["host"]
        name = "pakketjes" if carrier == "postnl" else "pakketjes-dhl"
        return None, (f"Geen sleutel voor {CARRIERS[carrier]['label']}. Vraag hem zo:\n"
                      f'  kluis vraag {name} --domein {host} "{CARRIERS[carrier]["label"]} API-sleutel"')
    if carrier == "postnl":
        return get_postnl(code, item)
    return get_dhl(code, item)


def parse_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    def flatten(node):
        out = {}
        for child in node:
            if len(child):
                out[child.tag] = flatten(child) if child.tag not in out else out[child.tag]
            else:
                out[child.tag] = child.text
        return out
    return flatten(root)


def print_result(result):
    label = CARRIERS[result["carrier"]]["label"]
    line = f"{result['code']} ({label}): {result.get('state') or 'onbekende status'}"
    if result.get("expected"):
        line += f" - verwacht {result['expected']}"
    print(line)
    if result.get("moment"):
        print(f"  laatst bijgewerkt: {result['moment']}")


def cmd_all(settings):
    parcels = settings.get("parcels", [])
    if not parcels:
        print("Nog geen pakketjes bewaard.")
        print("Voeg er een toe met: parcels add <code> [--vervoerder postnl|dhl]")
        print('Sleutels vraag je zo op: kluis vraag pakketjes --domein api.postnl.nl "PostNL API-sleutel"')
        return
    for parcel in parcels:
        code = parcel.get("code", "")
        carrier = carrier_of(parcel)
        if not carrier:
            print(f"{code}: vervoerder onbekend, gebruik parcels add {code} --vervoerder postnl|dhl")
            continue
        result, err = fetch(code, carrier)
        if err:
            print(f"{code} ({CARRIERS[carrier]['label']}): {err}")
        else:
            print_result(result)


def cmd_status(settings, code):
    carrier = None
    for parcel in settings.get("parcels", []):
        if parcel.get("code", "").lower() == code.lower():
            carrier = carrier_of(parcel)
            break
    if not carrier:
        carrier = guess_carrier(code)
    if not carrier:
        print(f"Vervoerder van {code} is onbekend. Gebruik: parcels status {code} --vervoerder postnl|dhl")
        return
    result, err = fetch(code, carrier)
    if err:
        print(err)
    else:
        print_result(result)


def cmd_add(settings, code, carrier):
    code = code.strip()
    if not code:
        print("Gebruik: parcels add <code> [--vervoerder postnl|dhl]")
        return
    if carrier and carrier not in CARRIERS:
        print("Vervoerder moet postnl of dhl zijn.")
        return
    if not carrier:
        carrier = guess_carrier(code)
    if not carrier:
        print(f"Ik herken de vervoerder van {code} niet. Voeg --vervoerder postnl of --vervoerder dhl toe.")
        return
    parcels = settings.get("parcels", [])
    if any(p.get("code", "").lower() == code.lower() for p in parcels):
        print(f"{code} staat al in de lijst.")
        return
    parcels.append({"code": code, "carrier": carrier})
    settings["parcels"] = parcels
    save_settings(settings)
    print(f"{code} ({CARRIERS[carrier]['label']}) toegevoegd.")


def cmd_remove(settings, code):
    parcels = settings.get("parcels", [])
    kept = [p for p in parcels if p.get("code", "").lower() != code.lower()]
    if len(kept) == len(parcels):
        print(f"{code} staat niet in de lijst.")
        return
    settings["parcels"] = kept
    save_settings(settings)
    print(f"{code} verwijderd.")


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return
    settings = load_settings()
    if not args or args[0] == "lijst":
        cmd_all(settings)
        return
    if args[0] == "add":
        rest = args[1:]
        carrier = None
        if "--vervoerder" in rest:
            i = rest.index("--vervoerder")
            if i + 1 < len(rest):
                carrier = rest[i + 1].lower()
            rest = rest[:i] + rest[i + 2:]
        if "--carrier" in rest:
            i = rest.index("--carrier")
            if i + 1 < len(rest):
                carrier = rest[i + 1].lower()
            rest = rest[:i] + rest[i + 2:]
        cmd_add(settings, " ".join(rest), carrier)
    elif args[0] in ("verwijder", "remove"):
        if len(args) < 2:
            print("Gebruik: parcels verwijder <code>")
            return
        cmd_remove(settings, args[1])
    elif args[0] == "status":
        if len(args) < 2:
            print("Gebruik: parcels status <code> [--vervoerder postnl|dhl]")
            return
        if "--vervoerder" in args:
            i = args.index("--vervoerder")
            carrier = args[i + 1].lower() if i + 1 < len(args) else None
            code = args[1]
            settings.setdefault("parcels", [])
            result, err = fetch(code, carrier) if carrier in CARRIERS else (None, "Vervoerder moet postnl of dhl zijn.")
            if err:
                print(err)
            else:
                print_result(result)
        else:
            cmd_status(settings, args[1])
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main()
