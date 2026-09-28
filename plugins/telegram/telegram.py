#!/usr/bin/env python3
"""Telegram for Iris, through @OkayIrisBot. The bot and its key live outside your workspace; this command asks
the connection.

  telegram            linked or not; not linked: a link to connect (also /telegram in the chat)
  telegram link       a fresh link: the owner opens it and taps Start in Telegram (works once, for an hour)
  telegram unlink     stop: nothing comes in from Telegram and nothing goes out there anymore

Once linked, what the owner sends on Telegram reaches you like a message on the page, and your answer goes
back there by itself. When the page is closed, what you say on your own (a reminder, a finished job) goes to
Telegram too. Only the owner's own chat is linked; nobody else can talk to you through the bot.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BRIDGE = os.environ.get("IRIS_BRIDGE_URL", "http://host.docker.internal:8790") + "/telegram"


def call(path="", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BRIDGE + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except ValueError:
            d = {}
        sys.exit(f"telegram: {d.get('error') or e.code}")
    except OSError as e:
        sys.exit(f"telegram: the connection cannot be reached ({e})")


def link():
    d = call("/link", {})
    print(f"Open this link on the phone or computer with Telegram, then tap Start:\n{d['link']}\n"
          "It works once, for an hour.")


a = sys.argv[1:]
if not a:
    if call()["linked"]:
        print("Telegram is linked. Messages there reach you; `telegram unlink` stops it.")
    else:
        link()
elif a == ["settings"]:
    # For the Integrations screen (settings.json): the current values as JSON.
    print(json.dumps({"connected": "on" if call()["linked"] else "off"}))
elif a[:3] == ["settings", "set", "connected"] and len(a) == 4:
    # Shown to the owner under the switch, so it talks to them.
    if a[3] == "off":
        call("/unlink", {})
        print("Telegram is unlinked.")
    elif call()["linked"]:
        print("Telegram is already linked.")
    else:
        link()
elif a == ["status"]:
    print("linked" if call()["linked"] else "not linked")
elif a == ["link"]:
    link()
elif a == ["unlink"]:
    call("/unlink", {})
    print("Telegram is unlinked")
else:
    sys.exit(__doc__)
