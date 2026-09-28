#!/usr/bin/env python3
"""Crypto prices through CoinGecko's public API: the coins you follow, one coin, or what an amount is worth.

  crypto                                the coins you follow, with the change over 24 hours
  crypto <coin>                         one coin: price, 24 hours, 7 days and market cap
  crypto <amount> <coin> [currency]     what an amount is worth, like: crypto 0.5 btc
  crypto add <coin> / remove <coin>     follow a coin, or stop
  crypto settings                       the values as JSON
  crypto settings set <key> <value>     change one value (currency, coins)

A coin is its symbol (btc, eth) or its name (bitcoin, solana). Prices only: this plugin never sees a
wallet or an exchange account, and it is not advice.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
IDS_FILE = os.path.join(HERE, ".ids.json")
API = "https://api.coingecko.com/api/v3/"
DEFAULT = {"currency": "eur", "coins": "bitcoin, ethereum"}
KNOWN = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "xrp": "ripple", "ada": "cardano",
         "doge": "dogecoin", "dot": "polkadot", "ltc": "litecoin", "usdt": "tether", "usdc": "usd-coin",
         "bnb": "binancecoin", "trx": "tron", "link": "chainlink", "avax": "avalanche-2", "xlm": "stellar"}


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
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def get(path, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "Iris-crypto/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            sys.exit("CoinGecko asks to slow down. Try again in a minute.")
        sys.exit(f"CoinGecko answered with status {exc.code}.")
    except (OSError, ValueError):
        sys.exit("CoinGecko did not answer. Try again in a minute.")


def cached_ids():
    try:
        with open(IDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def coin_id(text):
    """A symbol or name to CoinGecko's id and a display name."""
    key = text.strip().lower()
    ids = cached_ids()
    if key in ids:
        return ids[key]
    found = None
    data = get("search", query=key)
    coins = data.get("coins") or []
    # An exact symbol or name wins; among those, the biggest (lowest market cap rank).
    exact = [c for c in coins if c.get("symbol", "").lower() == key or c.get("name", "").lower() == key
             or c.get("id") == key]
    exact.sort(key=lambda c: c.get("market_cap_rank") or 10**9)
    pick = exact[0] if exact else (coins[0] if coins else None)
    if pick:
        found = {"id": pick["id"], "name": pick["name"], "symbol": pick["symbol"].upper()}
    elif key in KNOWN:
        found = {"id": KNOWN[key], "name": KNOWN[key].capitalize(), "symbol": key.upper()}
    if not found:
        sys.exit(f"CoinGecko knows no coin called {text}.")
    ids[key] = found
    try:
        with open(IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(ids, f)
    except OSError:
        pass
    return found


def currency():
    cur = values()["currency"].strip().lower()
    return cur if re.fullmatch(r"[a-z]{3,4}", cur) else "eur"


def price_text(value, cur):
    if value is None:
        return "?"
    decimals = 2 if value >= 1 else 6 if value >= 0.0001 else 10
    return f"{value:,.{decimals}f} {cur.upper()}"


def change(pct):
    if pct is None:
        return ""
    return f"{'up' if pct >= 0 else 'down'} {abs(pct):.1f}%"


def followed():
    return [c.strip() for c in values()["coins"].split(",") if c.strip()]


# --- commands -------------------------------------------------------------------------------------

def cmd_watch():
    names = followed()
    if not names:
        print("You follow no coins. Add one with: crypto add <coin>.")
        return
    cur = currency()
    coins = [coin_id(n) for n in names]
    data = get("simple/price", ids=",".join(c["id"] for c in coins), vs_currencies=cur, include_24hr_change="true")
    for c in coins:
        row = data.get(c["id"]) or {}
        moved = change(row.get(f"{cur}_24h_change"))
        print(f"{c['name']} ({c['symbol']}): {price_text(row.get(cur), cur)}" + (f", {moved} in 24 hours" if moved else ""))


def cmd_coin(text):
    c = coin_id(text)
    cur = currency()
    rows = get("coins/markets", vs_currency=cur, ids=c["id"], price_change_percentage="24h,7d,30d")
    if not rows:
        sys.exit(f"No market price for {c['name']}.")
    r = rows[0]
    print(f"{r['name']} ({r['symbol'].upper()}): {price_text(r.get('current_price'), cur)}.")
    parts = [f"{label} {change(r.get(key))}" for label, key in
             (("24 hours", "price_change_percentage_24h_in_currency"), ("7 days", "price_change_percentage_7d_in_currency"),
              ("30 days", "price_change_percentage_30d_in_currency")) if r.get(key) is not None]
    if parts:
        print("Over " + ", ".join(parts) + ".")
    if r.get("market_cap"):
        rank = f", number {r['market_cap_rank']}" if r.get("market_cap_rank") else ""
        print(f"Market cap {r['market_cap'] / 1e9:,.1f} billion {cur.upper()}{rank}.")
    if r.get("ath") and r.get("ath_change_percentage") is not None:
        print(f"All-time high {price_text(r['ath'], cur)}, now {abs(r['ath_change_percentage']):.0f}% below it.")


def cmd_amount(args):
    try:
        amount = float(args[0].replace(",", "."))
    except ValueError:
        sys.exit(f"{args[0]} is not an amount.")
    words = [w for w in args[1:] if w.lower() not in ("in", "to")]
    if not words:
        sys.exit("crypto <amount> <coin> [currency]")
    cur = currency()
    if len(words) > 1 and re.fullmatch(r"[A-Za-z]{3,4}", words[-1]) and words[-1].lower() in (
            "eur", "usd", "gbp", "chf", "jpy", "cad", "aud", "sek", "nok", "dkk", "pln", "btc", "eth"):
        cur = words.pop().lower()
    c = coin_id(" ".join(words))
    data = get("simple/price", ids=c["id"], vs_currencies=cur)
    price = (data.get(c["id"]) or {}).get(cur)
    if price is None:
        sys.exit(f"No price for {c['name']} in {cur.upper()}.")
    print(f"{amount:g} {c['symbol']} is {price_text(amount * price, cur)} (1 {c['symbol']} = {price_text(price, cur)}).")


def cmd_follow(args, on):
    if not args:
        sys.exit(f"crypto {'add' if on else 'remove'} <coin>")
    c = coin_id(" ".join(args))
    names = followed()
    ids = {n: coin_id(n)["id"] for n in names}
    if on:
        if c["id"] in ids.values():
            print(f"You already follow {c['name']}.")
            return
        keep("coins", ", ".join(names + [c["id"]]))
        print(f"Following {c['name']}.")
    else:
        kept = [n for n in names if ids[n] != c["id"]]
        if len(kept) == len(names):
            sys.exit(f"You do not follow {c['name']}.")
        keep("coins", ", ".join(kept))
        print(f"No longer following {c['name']}.")


def cmd_settings(args):
    if not args:
        print(json.dumps(values()))
        return
    if len(args) < 3 or args[0] != "set":
        sys.exit("crypto settings set <currency|coins> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "currency":
        if not re.fullmatch(r"[A-Za-z]{3,4}", value):
            sys.exit("A currency is three letters, like EUR or USD.")
        supported = get("simple/supported_vs_currencies")
        if value.lower() not in supported:
            sys.exit(f"CoinGecko has no prices in {value.upper()}.")
        keep("currency", value.lower())
        print(f"Prices in {value.upper()}.")
    elif key == "coins":
        coins = [coin_id(c) for c in value.split(",") if c.strip()]
        keep("coins", ", ".join(c["id"] for c in coins))
        print(f"Following {', '.join(c['name'] for c in coins) or 'no coins'}.")
    else:
        sys.exit(f"There is no setting called {key}. Use currency or coins.")


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_watch()
    elif cmd == "add":
        cmd_follow(rest, True)
    elif cmd == "remove":
        cmd_follow(rest, False)
    elif cmd == "settings":
        cmd_settings(rest)
    elif re.fullmatch(r"[\d.,]+", cmd):
        cmd_amount(argv)
    else:
        cmd_coin(" ".join(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
