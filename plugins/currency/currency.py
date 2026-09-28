#!/usr/bin/env python3
"""Money in another currency, at the reference rates of the European Central Bank (via Frankfurter).

  currency <amount> <from> [to]         convert, like `currency 25 USD EUR` or `currency 25 usd`
  currency rates [base]                 today's rates of your usual currencies
  currency history <from> <to> [days]   how a rate moved, 30 days by default
  currency list                         the currencies that are known
  currency settings                     the values as JSON
  currency settings set <key> <value>   change one value (home, watch)

Rates are published once every working day around 16:00 CET. No key and no account.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
VALUES_FILE = os.path.join(HERE, "values.json")
API = "https://api.frankfurter.dev/v1/"
DEFAULT = {"home": "EUR", "watch": "USD, GBP, CHF, JPY"}
ALIASES = {"€": "EUR", "euro": "EUR", "euros": "EUR", "$": "USD", "dollar": "USD", "dollars": "USD",
           "£": "GBP", "pound": "GBP", "pounds": "GBP", "¥": "JPY", "yen": "JPY", "franc": "CHF",
           "francs": "CHF", "kronor": "SEK", "krone": "NOK", "zloty": "PLN", "yuan": "CNY"}


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
    tmp = VALUES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, VALUES_FILE)


def get(path, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "Iris-currency/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 422):
            sys.exit("One of those currencies is not known. `currency list` shows them.")
        sys.exit(f"The rate service answered with status {exc.code}. Try again in a minute.")
    except (OSError, ValueError):
        sys.exit("The rate service did not answer. Try again in a minute.")


def code(text):
    t = text.strip()
    if t.lower() in ALIASES or t in ALIASES:
        return ALIASES.get(t.lower(), ALIASES.get(t))
    if re.fullmatch(r"[A-Za-z]{3}", t):
        return t.upper()
    sys.exit(f"{text} is not a currency code. Use three letters, like EUR or USD.")


def amount(text):
    t = text.replace("_", "").replace(" ", "")
    # 1.234,56 and 1,234.56 both mean one thousand two hundred and thirty four.
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = head.replace(",", "") + ("." + tail if len(tail) != 3 else tail)
    try:
        return float(t)
    except ValueError:
        return None


def money(value, cur):
    decimals = 0 if cur in ("JPY", "KRW", "HUF", "ISK", "IDR") else 2
    text = f"{value:,.{decimals}f}"
    return f"{text} {cur}"


def watched():
    return [code(c) for c in values()["watch"].split(",") if c.strip()]


# --- commands -------------------------------------------------------------------------------------

def cmd_convert(args):
    # Accept "25 USD EUR", "25 USD to EUR", "25USD in EUR", "USD 25".
    words = [w for w in args if w.lower() not in ("to", "in", "into", "naar")]
    joined = " ".join(words)
    m = re.match(r"^\s*([^\d\s]*)\s*([\d.,_]+)\s*([^\d\s]*)\s*(.*)$", joined)
    if not m:
        sys.exit("currency <amount> <from> [to], like: currency 25 USD EUR")
    pre, num, post, rest = m.groups()
    value = amount(num)
    if value is None:
        sys.exit(f"{num} is not an amount.")
    source = code(post or pre) if (post or pre) else None
    if not source:
        sys.exit("Which currency is that amount in? Like: currency 25 USD.")
    home = code(values()["home"])
    targets = [code(t) for t in rest.split()] if rest.strip() else ([home] if source != home else watched())
    targets = [t for t in targets if t != source]
    if not targets:
        print(money(value, source))
        return
    data = get("latest", base=source, symbols=",".join(targets))
    parts = [money(value * data["rates"][t], t) for t in targets if t in data.get("rates", {})]
    if not parts:
        sys.exit("One of those currencies is not known. `currency list` shows them.")
    print(f"{money(value, source)} is {', '.join(parts)} (rate of {data['date']}).")


def cmd_rates(args):
    base = code(args[0]) if args else code(values()["home"])
    targets = [t for t in watched() if t != base] or ["USD"]
    data = get("latest", base=base, symbols=",".join(targets))
    print(f"1 {base} on {data['date']}:")
    for t in targets:
        if t in data["rates"]:
            print(f"  {data['rates'][t]:.4f} {t}")


def cmd_history(args):
    if len(args) < 2:
        sys.exit("currency history <from> <to> [days]")
    source, target = code(args[0]), code(args[1])
    days = int(args[2]) if len(args) > 2 and args[2].isdigit() else 30
    days = max(2, min(days, 3650))
    start = (date.today() - timedelta(days=days)).isoformat()
    data = get(f"{start}..", base=source, symbols=target)
    series = [(d, r[target]) for d, r in sorted(data.get("rates", {}).items()) if target in r]
    if len(series) < 2:
        sys.exit("Not enough rates in that period.")
    first, last = series[0], series[-1]
    low = min(series, key=lambda x: x[1])
    high = max(series, key=lambda x: x[1])
    change = (last[1] - first[1]) / first[1] * 100
    direction = "up" if change > 0 else "down" if change < 0 else "flat"
    print(f"1 {source} in {target}, the last {days} days: {first[1]:.4f} on {first[0]}, "
          f"{last[1]:.4f} on {last[0]}; {direction} {abs(change):.1f}%.")
    print(f"Lowest {low[1]:.4f} on {low[0]}, highest {high[1]:.4f} on {high[0]}.")


def cmd_list():
    data = get("currencies")
    print(f"{len(data)} currencies:")
    for k, v in sorted(data.items()):
        print(f"  {k}  {v}")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 3 or args[0] != "set":
        sys.exit("currency settings set <home|watch> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "home":
        keep("home", code(value))
        print(f"Your own currency is {code(value)}.")
    elif key == "watch":
        codes = [code(c) for c in value.split(",") if c.strip()]
        keep("watch", ", ".join(codes))
        print(f"Watching {', '.join(codes)}.")
    else:
        sys.exit(f"There is no setting called {key}. Use home or watch.")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif argv[0] == "rates":
        cmd_rates(argv[1:])
    elif argv[0] == "history":
        cmd_history(argv[1:])
    elif argv[0] == "list":
        cmd_list()
    elif argv[0] == "settings":
        cmd_settings(argv[1:])
    else:
        cmd_convert(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
