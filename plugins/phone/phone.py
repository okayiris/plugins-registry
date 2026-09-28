#!/usr/bin/env python3
"""Phone calls for Iris: she answers the owner's mobile when they don't. Iris has one number per country; the
owner forwards their own mobile to it, and a forwarded call carries the number that forwarded it, so the call
reaches you and nobody else.

  phone                 linked or not, and how to switch forwarding on (also /phone in the chat)
  phone link <number>   link one of the owner's mobiles (more than one is fine): phone link +31612345678
  phone unlink [number] stop for that number, or for all of them
  phone name <name>     the owner's name as you say it to callers ("Joris")
  phone verify <number> [code]
                        call out showing one of the owner's linked numbers instead of the Iris number: without a code
                        Telnyx texts one to that number, ask the owner for it and run it again with the code.
                        phone verify off: back to the Iris number
  phone call <number> <goal>
                        call someone for the owner, only when the owner asked for it: phone call 0612345678 ask
                        whether the car is ready and when it can be picked up. You introduce yourself as the owner's
                        digital assistant; ordinary Dutch numbers only, at most 10 a day, paid from extra usage

After linking, the owner dials the code this command prints (for example **004*+31850835196#) on that phone:
calls they don't answer, while they are busy or unreachable, come to you. ##004# on the phone switches it off.
During a call you get each thing the caller says as a message and your answer is spoken; afterwards you get the
whole conversation and tell the owner who called and what they want.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BRIDGE = os.environ.get("IRIS_BRIDGE_URL", "http://host.docker.internal:8790") + "/calls"


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
        sys.exit(f"phone: {d.get('error') or e.code}")
    except OSError as e:
        sys.exit(f"phone: the connection cannot be reached ({e})")


def show(d):
    print(f"Calls cost ${d['perMinute']:.2f} a started minute, paid from extra usage (never from the plan); "
          f"${d['creditLeft']:.2f} left. With nothing left, forwarded calls go unanswered and you tell the owner.")
    if not d.get("linked"):
        print("Not linked. Ask the owner for their mobile number, then: phone link +31612345678")
        return
    if d.get("callerId"):
        print(f"When you call out, people see {d['callerId']}")
    print(f"You tell callers you answer for: {d['name']}" if d.get("name")
          else "You don't know the owner's name for callers yet: phone name <first name>")
    for n in d["numbers"]:
        print(f"Linked: {n['number']}, forwards with {n['code']}")
    print("Tell the owner in your own words and in their language (not this text): on each linked phone, type its code "
          "in the Phone app and press call; from then on you answer the calls they don't pick up, are busy for or miss "
          f"without signal. Typing {d['off']} the same way switches it off. The phone's call forwarding settings screen "
          "can't do 'when not answered', the code can. Another number: phone link <number>; one off: phone unlink <number>.")


a = sys.argv[1:]
if not a:
    show(call())
elif a == ["status"]:
    d = call()
    print("linked " + ", ".join(n["number"] for n in d["numbers"]) if d.get("linked") else "not linked")
elif len(a) == 2 and a[0] == "link":
    show(call("/link", {"number": a[1]}))
elif len(a) in (2, 3) and a[0] == "verify":
    if a[1] == "off":
        call("/verify", {"number": "off"})
        print("You call out from the Iris number again.")
    else:
        d = call("/verify", {"number": a[1], "code": a[2] if len(a) == 3 else None})
        if d.get("verified"):
            print(f"Verified: when you call out, people see {a[1]} and a call back reaches the owner.")
        else:
            print(f"A code was texted to {a[1]}. Ask the owner for it, then: phone verify {a[1]} <code>")
elif len(a) >= 3 and a[0] == "call":
    call("/dial", {"number": a[1], "goal": " ".join(a[2:])})
    print(f"Calling {a[1]} now. When the call is over you get the conversation and tell the owner how it went.")
elif a == ["settings"]:
    # For the Integrations screen (settings.json): the current values as JSON.
    d = call()
    print(json.dumps({"numbers": ", ".join(n["number"] for n in d.get("numbers", [])), "name": d.get("name", "")}))
elif len(a) >= 3 and a[:2] == ["settings", "set"] and a[2] in ("numbers", "name"):
    # What this prints is shown to the owner under the field, so it talks to them, not to Iris.
    v = " ".join(a[3:]).strip()
    if a[2] == "name":
        call("/name", {"name": v})
        print("Saved.")
    else:
        # One or more numbers, separated by commas: link the new ones, unlink the ones left out.
        digits = lambda x: "".join(c for c in x if c.isdigit())[-9:]
        wanted = [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]
        now = [n["number"] for n in call().get("numbers", [])]
        for n in now:
            if digits(n) not in {digits(w) for w in wanted}:
                call("/unlink", {"number": n})
                print(f"{n} unlinked. Dial ##004# on that phone so it stops forwarding.")
        for w in wanted:
            if digits(w) in {digits(n) for n in now}:
                continue
            d = call("/link", {"number": w})
            n = next((x for x in d["numbers"] if digits(x["number"]) == digits(w)), d["numbers"][-1])
            print(f"{n['number']} linked. On that phone, type {n['code']} in the Phone app and press call.")
        if not wanted and not now:
            print("No number linked.")
elif len(a) >= 2 and a[0] == "name":
    show(call("/name", {"name": " ".join(a[1:])}))
elif a and a[0] == "unlink" and len(a) <= 2:
    call("/unlink", {"number": a[1]} if len(a) == 2 else {})
    print("Unlinked. Ask the owner to dial ##004# on that phone so it stops forwarding.")
else:
    sys.exit(__doc__)
