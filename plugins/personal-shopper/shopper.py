#!/usr/bin/env python3
"""A personal shopper: search the shops you like all at once, keep a cart across them, and order.

  shopper search <what> [--max N] [--min N] [--shop <name>]
                                        search every shop you follow at once
  shopper results                       the last results again
  shopper show <n>                      one result in full, with its sizes or colours
  shopper add <n|link> [option] [x2]    into the cart, like: shopper add 3 10.5 x2 (size 10.5, two)
                                        a link works for a product in any shop
  shopper cart                          the cart, per shop
  shopper qty <line> <qty>              change how many (0 removes the line)
  shopper remove <line> / shopper clear take a line out, or empty the cart
  shopper save <n|link>                 keep a product to decide later
  shopper saved                         the kept products, with their price now
  shopper order [shop]                  what would be ordered, per shop; nothing happens yet
  shopper order --yes [shop]            after the owner's yes: the checkout links, per shop
  shopper orders                        what was ordered before
  shopper shops                         the shops you follow, and what kind each is
  shopper shops add <link> [name]       follow a shop (Shopify and WooCommerce shops can be searched)
  shopper shops remove <name>           stop following one
  shopper settings                      the values as JSON
  shopper settings set <key> <value>    change one value

Add --json to search, results, show, add, cart, saved, order and orders for the screen.

How ordering works: nothing is bought here. `order --yes` turns the cart into one link per shop that
opens that shop's own checkout with the products already in it (Shopify), or adds them to the shop's
cart (WooCommerce), or opens the product page (any other shop). The owner pays there, on the shop's
own page. This plugin never sees a password, a card or an account.
"""
import concurrent.futures
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
SHOPS_FILE = os.path.join(HERE, ".shops.json")
RESULTS_FILE = os.path.join(HERE, ".results.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 Iris-shopper/1.0"
DEFAULT = {"shops": "", "per_shop": "8", "about": ""}
JSON_OUT = "--json" in sys.argv


class Stop(Exception):
    pass


def fail(msg):
    raise Stop(msg)


# --- values and small files -----------------------------------------------------------------------

def load(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(fallback)) else fallback
    except (OSError, ValueError):
        return fallback


def save(path, data):
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(path + ".tmp", path)


def values():
    out = dict(DEFAULT)
    out.update({str(k): str(v) for k, v in load(VALUES_FILE, {}).items()})
    return out


def keep(key, value):
    data = load(VALUES_FILE, {})
    data[key] = value
    save(VALUES_FILE, data)


def base_url(link):
    link = link.strip()
    if not re.match(r"^https?://", link):
        link = "https://" + link
    p = urllib.parse.urlparse(link)
    if not p.netloc or "." not in p.netloc:
        fail(f"{link} is not a web address.")
    return f"{p.scheme}://{p.netloc}"


def shops():
    """The shops followed, as dicts with name, url and (once known) kind and currency."""
    meta = load(SHOPS_FILE, {})
    out = []
    for part in values()["shops"].split(","):
        name, _, link = part.strip().rpartition("|")
        if not link.strip():
            continue
        try:
            url = base_url(link)
        except Stop:
            continue
        info = meta.get(url, {})
        out.append({"name": name.strip() or urllib.parse.urlparse(url).netloc.replace("www.", ""),
                    "url": url, "kind": info.get("kind", ""), "currency": info.get("currency", "")})
    return out


def store_shops(items):
    keep("shops", ", ".join(f"{s['name']}|{s['url']}" for s in items))


# --- the web --------------------------------------------------------------------------------------

def fetch(url, timeout=15, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "nl,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(6_000_000).decode("utf-8", "replace"), resp.geturl()


def fetch_json(url, timeout=15):
    body, _ = fetch(url, timeout)
    return json.loads(body)


def plain(text, limit=None):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "..."
    return t


def cents(value):
    try:
        return round(float(str(value).replace(",", ".")) * 100)
    except (TypeError, ValueError):
        return None


def detect(url):
    """What kind of shop this is: shopify, woo, or None when it has no open search."""
    try:
        data = fetch_json(url + "/search/suggest.json?q=a&resources%5Btype%5D=product&resources%5Blimit%5D=1")
        if "resources" in data:
            currency = ""
            try:
                currency = fetch_json(url + "/cart.js").get("currency", "")
            except (OSError, ValueError, urllib.error.URLError):
                pass
            return {"kind": "shopify", "currency": currency}
    except (OSError, ValueError, urllib.error.URLError):
        pass
    try:
        data = fetch_json(url + "/wp-json/wc/store/v1/products?per_page=1")
        if isinstance(data, list):
            currency = data[0]["prices"]["currency_code"] if data else ""
            return {"kind": "woo", "currency": currency}
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        pass
    return None


def known(shop):
    """Fill in the kind of a shop, once, and remember it."""
    if shop["kind"]:
        return shop
    info = detect(shop["url"])
    meta = load(SHOPS_FILE, {})
    meta[shop["url"]] = info or {"kind": "none", "currency": ""}
    save(SHOPS_FILE, meta)
    return dict(shop, **(info or {"kind": "none"}))


# --- searching ------------------------------------------------------------------------------------

def search_shopify(shop, query, limit):
    q = urllib.parse.urlencode({"q": query, "resources[type]": "product", "resources[limit]": min(limit, 10),
                                "resources[options][unavailable_products]": "last"})
    data = fetch_json(f"{shop['url']}/search/suggest.json?{q}")
    out = []
    for p in ((data.get("resources") or {}).get("results") or {}).get("products") or []:
        image = p.get("image") or (p.get("featured_image") or {}).get("url") or ""
        price, was = cents(p.get("price")), cents(p.get("compare_at_price_max"))
        out.append({
            "shop": shop["name"], "shop_url": shop["url"], "kind": "shopify",
            "id": str(p.get("id", "")), "handle": p.get("handle", ""),
            "title": p.get("title", "?"), "brand": p.get("vendor", ""),
            "price": price, "was": was if was and price and was > price else None,
            "currency": shop.get("currency") or "", "available": bool(p.get("available")),
            "image": image if not image.startswith("//") else "https:" + image,
            "url": shop["url"] + (p.get("url") or f"/products/{p.get('handle', '')}").split("?")[0],
            "text": plain(p.get("body"), 300),
        })
    return out


def search_woo(shop, query, limit):
    q = urllib.parse.urlencode({"search": query, "per_page": min(limit, 20)})
    data = fetch_json(f"{shop['url']}/wp-json/wc/store/v1/products?{q}")
    out = []
    for p in data if isinstance(data, list) else []:
        prices = p.get("prices") or {}
        unit = 10 ** int(prices.get("currency_minor_unit", 2))
        price, regular = (round(int(v) * 100 / unit) if v_ok(v) else None
                          for v in (prices.get("price"), prices.get("regular_price")))
        images = p.get("images") or []
        out.append({
            "shop": shop["name"], "shop_url": shop["url"], "kind": "woo",
            "id": str(p.get("id", "")), "handle": p.get("slug", ""),
            "title": plain(p.get("name")) or "?", "brand": "",
            "price": price, "was": regular if regular and price and regular > price else None,
            "currency": prices.get("currency_code") or shop.get("currency") or "",
            "available": bool(p.get("is_in_stock")) and bool(p.get("is_purchasable", True)),
            "image": images[0].get("src", "") if images else "",
            "url": p.get("permalink", ""), "text": plain(p.get("short_description") or p.get("description"), 300),
            "variable": p.get("type") == "variable",
        })
    return out


def v_ok(v):
    return v not in (None, "") and str(v).lstrip("-").isdigit()


def search_all(query, only=None, limit=8):
    targets = [s for s in shops() if not only or only.lower() in s["name"].lower()]
    if not targets:
        fail("You follow no shops yet. Follow one with: shopper shops add <link>." if not only
             else f"You follow no shop called {only}.")

    def one(shop):
        shop = known(shop)
        if shop["kind"] == "shopify":
            return shop, search_shopify(shop, query, limit)
        if shop["kind"] == "woo":
            return shop, search_woo(shop, query, limit)
        return shop, None

    per_shop, problems = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one, s) for s in targets]
        for fut, shop in zip(futures, targets):
            try:
                s, items = fut.result(timeout=40)
                if items is None:
                    problems.append({"shop": s["name"], "why": "no_search"})
                    continue
                buyable = [i for i in items if i["price"] or i["available"]]
                for i in buyable:
                    i["price"] = i["price"] or None
                if items and not buyable:
                    problems.append({"shop": s["name"], "why": "not_selling"})
                per_shop.append(buyable[:limit])
            except Exception:  # one shop down never spoils the others
                problems.append({"shop": shop["name"], "why": "down"})
    # Take turns between the shops, so the best of each comes first.
    mixed = []
    for i in range(max((len(x) for x in per_shop), default=0)):
        for items in per_shop:
            if i < len(items):
                mixed.append(items[i])
    return mixed, problems


# --- one product ----------------------------------------------------------------------------------

def shopify_variants(item):
    data = fetch_json(f"{item['shop_url']}/products/{item['handle']}.js")
    names = data.get("options") or []
    names = [o.get("name") if isinstance(o, dict) else o for o in names]
    out = []
    for v in data.get("variants") or []:
        title = v.get("public_title") or v.get("title") or ""
        out.append({"id": str(v["id"]), "title": "" if title == "Default Title" else title,
                    "price": v.get("price"), "available": bool(v.get("available"))})
    return names, out


def from_link(link):
    """Any product page: Shopify and WooCommerce directly, else the schema.org data in the page."""
    url = link.strip()
    if not re.match(r"^https?://", url):
        fail("A product link starts with https://.")
    root = base_url(url)
    m = re.search(r"/products/([^/?#]+)", url)
    if m:
        try:
            data = fetch_json(f"{root}/products/{m.group(1)}.js")
            meta = detect(root) or {}
            return {"shop": shop_name(root), "shop_url": root, "kind": "shopify", "id": str(data["id"]),
                    "handle": data["handle"], "title": data["title"], "brand": data.get("vendor", ""),
                    "price": data.get("price"), "was": data.get("compare_at_price") or None,
                    "currency": meta.get("currency", ""), "available": bool(data.get("available")),
                    "image": ("https:" + data["featured_image"]) if str(data.get("featured_image", "")).startswith("//")
                    else data.get("featured_image", ""), "url": root + f"/products/{data['handle']}",
                    "text": plain(data.get("description"), 300)}
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            pass
    try:
        page, final = fetch(url, 20, "text/html,application/xhtml+xml")
    except urllib.error.HTTPError as exc:
        fail(f"The shop turned the request away ({exc.code}). Some big shops do that; open the link yourself.")
    except (OSError, urllib.error.URLError):
        fail("That page could not be read.")
    product = None
    for block in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for x in stack:
            if isinstance(x, dict) and "Product" in str(x.get("@type")):
                product = x
                break
        if product:
            break
    if not product:
        fail("That page does not describe a product in a way I can read.")
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if offers.get("@type") == "AggregateOffer":
        offers = dict(offers, price=offers.get("lowPrice"))
    image = product.get("image")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url", "")
    brand = product.get("brand")
    brand = brand.get("name", "") if isinstance(brand, dict) else (brand or "")
    return {"shop": shop_name(root), "shop_url": root, "kind": "link", "id": str(product.get("sku") or ""),
            "handle": "", "title": plain(product.get("name")) or "?", "brand": brand,
            "price": cents(offers.get("price")), "was": None, "currency": offers.get("priceCurrency", ""),
            "available": "InStock" in str(offers.get("availability", "InStock")) or "LimitedAvailability" in str(offers.get("availability")),
            "image": image or "", "url": final or url, "text": plain(product.get("description"), 300)}


def shop_name(root):
    for s in shops():
        if s["url"] == root:
            return s["name"]
    host = urllib.parse.urlparse(root).netloc.replace("www.", "")
    return host.split(".")[0].capitalize()


def pick(ref):
    """A result number from the last search, or a product link."""
    if re.match(r"^https?://", ref):
        return from_link(ref)
    if not ref.isdigit():
        fail("Give the number of a result, or a product link.")
    last = load(RESULTS_FILE, {}).get("items") or []
    n = int(ref)
    if not 1 <= n <= len(last):
        fail("That number is not in the last results. Search first.")
    return last[n - 1]


# --- money ----------------------------------------------------------------------------------------

def money(c, cur):
    if c is None:
        return "price unknown"
    return f"{c / 100:,.2f} {cur}".strip()


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    if not con.execute("select 1 from sqlite_master where type='table' and name='cart'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def out(data, text):
    """The screen gets JSON, the conversation gets text."""
    if JSON_OUT:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(text.rstrip())


# --- commands -------------------------------------------------------------------------------------

def cmd_search(args):
    words, only, lo, hi = [], None, None, None
    it = iter(args)
    for a in it:
        if a == "--shop":
            only = next(it, None)
        elif a in ("--max", "--min"):
            value = cents(next(it, ""))
            if value is None:
                fail(f"{a} needs an amount.")
            hi, lo = (value, lo) if a == "--max" else (hi, value)
        elif a != "--json":
            words.append(a)
    query = " ".join(words).strip()
    if not query:
        fail("shopper search <what>")
    limit = max(1, min(int(values()["per_shop"] or 8), 20))
    items, problems = search_all(query, only, limit)
    if hi is not None:
        items = [i for i in items if i["price"] is not None and i["price"] <= hi]
    if lo is not None:
        items = [i for i in items if i["price"] is not None and i["price"] >= lo]
    save(RESULTS_FILE, {"query": query, "at": time.time(), "items": items, "problems": problems})
    show_results(query, items, problems)


def show_results(query, items, problems):
    lines = []
    if items:
        lines.append(f"{len(items)} results for {query}:")
        for n, i in enumerate(items, 1):
            sale = f" (was {money(i['was'], i['currency'])})" if i.get("was") else ""
            stock = "" if i["available"] else ", sold out"
            lines.append(f"{n:>2}. {i['title']}, {money(i['price'], i['currency'])}{sale}  [{i['shop']}{stock}]")
        lines.append("Say `shopper add <number>` to put one in the cart, or open the screen to browse.")
    else:
        lines.append(f"Nothing found for {query}.")
    if problems:
        why = {"no_search": "no open search; add its products by link",
               "not_selling": "shows products but sells none through its web shop", "down": "did not answer"}
        lines.append("Not searched: " + "; ".join(f"{p['shop']} ({why.get(p['why'], p['why'])})" for p in problems) + ".")
    out({"query": query, "items": items, "problems": problems}, "\n".join(lines))


def cmd_results():
    last = load(RESULTS_FILE, {})
    if not last:
        out({"query": "", "items": [], "problems": []}, "No search yet. Say: shopper search <what>.")
        return
    show_results(last.get("query", ""), last.get("items") or [], last.get("problems") or [])


def cmd_show(args):
    refs = [a for a in args if a != "--json"]
    if not refs:
        fail("shopper show <n>")
    item = pick(refs[0])
    options, variants = [], []
    if item["kind"] == "shopify":
        try:
            options, variants = shopify_variants(item)
        except (OSError, ValueError, urllib.error.URLError):
            pass
    lines = [f"{item['title']}" + (f" by {item['brand']}" if item.get("brand") else "") + f", {item['shop']}",
             f"{money(item['price'], item['currency'])}" + ("" if item["available"] else ", sold out")]
    if item.get("text"):
        lines.append(item["text"])
    choices = [v for v in variants if v["title"]]
    if choices:
        free = [v["title"] for v in choices if v["available"]]
        gone = [v["title"] for v in choices if not v["available"]]
        lines.append(f"{', '.join(options) or 'Options'}: " + (", ".join(free) or "none in stock")
                     + (f" (sold out: {', '.join(gone)})" if gone else ""))
    lines.append(item["url"])
    out(dict(item, options=options, variants=variants), "\n".join(lines))


def choose_variant(item, wanted):
    """The Shopify variant meant by the words, or the only one there is."""
    options, variants = shopify_variants(item)
    real = [v for v in variants if v["title"]]
    if not real:
        return variants[0] if variants else None, None
    if wanted:
        w = wanted.lower().replace(" ", "")
        exact = [v for v in real if v["title"].lower().replace(" ", "") == w]
        parts = [v for v in real if all(p in v["title"].lower().replace(" ", "").split("/") or p in v["title"].lower()
                                        for p in wanted.lower().split())]
        hits = exact or parts
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, {"need": "variant", "options": options, "variants": hits,
                          "message": f"Several fit: {', '.join(v['title'] for v in hits)}. Which one?"}
        return None, {"need": "variant", "options": options, "variants": real,
                      "message": f"{wanted} is not one of them: {', '.join(v['title'] for v in real)}."}
    free = [v for v in real if v["available"]]
    if len(free) == 1:
        return free[0], None
    return None, {"need": "variant", "options": options, "variants": real,
                  "message": f"Which {' and '.join(o.lower() for o in options) or 'option'}? "
                             + ", ".join(v["title"] + ("" if v["available"] else " (sold out)") for v in real) + "."}


def cmd_add(args, to_saved=False):
    args = [a for a in args if a != "--json"]
    if not args:
        fail(f"shopper {'save' if to_saved else 'add'} <n|link> [option] [x2]")
    item = pick(args[0])
    rest, qty, variant_id = [], 1, ""
    words = iter(args[1:])
    for w in words:
        m = re.fullmatch(r"(?:x(\d{1,2})|(\d{1,2})x)", w.lower())
        if m:
            qty = int(m.group(1) or m.group(2))
        elif w == "--qty":
            n = next(words, "1")
            qty = int(n) if n.isdigit() else 1
        elif w == "--variant":
            variant_id = next(words, "")
        else:
            rest.append(w)
    qty = max(1, min(qty, 99))
    wanted = " ".join(rest).strip()
    variant = {"id": "", "title": "", "price": item["price"], "available": item["available"]}
    if item["kind"] == "shopify" and not to_saved:
        try:
            if variant_id:
                chosen = next((v for v in shopify_variants(item)[1] if v["id"] == variant_id), None)
                question = None if chosen else {"need": "variant", "options": [], "variants": [],
                                                "message": "That option is not there any more."}
            else:
                chosen, question = choose_variant(item, wanted)
        except (OSError, ValueError, urllib.error.URLError):
            fail(f"{item['shop']} did not answer. Try again in a minute.")
        if question:
            out(dict(question, item=item), question["message"] + f" Say: shopper add {args[0]} <choice>.")
            return
        variant = chosen or variant
        if not variant.get("available", True):
            fail(f"{item['title']} {variant['title']} is sold out.".replace("  ", " "))
    elif not item["available"] and not to_saved:
        fail(f"{item['title']} is sold out at {item['shop']}.")
    with db() as con:
        if to_saved:
            con.execute("insert or ignore into saved (shop, shop_url, kind, product_id, handle, title, price, currency, "
                        "image, url, first_price, added) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (item["shop"], item["shop_url"], item["kind"], item["id"], item["handle"], item["title"],
                         item["price"], item["currency"], item["image"], item["url"], item["price"],
                         datetime.now().isoformat(timespec="seconds")))
            out({"ok": True, "saved": item}, f"Kept {item['title']} from {item['shop']} at {money(item['price'], item['currency'])}.")
            return
        row = con.execute("select id, qty from cart where url = ? and variant_id = ?", (item["url"], variant["id"])).fetchone()
        if row:
            con.execute("update cart set qty = qty + ? where id = ?", (qty, row["id"]))
        else:
            con.execute("insert into cart (shop, shop_url, kind, product_id, variant_id, variant, title, price, currency, "
                        "image, url, qty, added) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (item["shop"], item["shop_url"], item["kind"], item["id"], variant["id"], variant["title"],
                         item["title"], variant.get("price") if variant.get("price") is not None else item["price"],
                         item["currency"], item["image"], item["url"], qty, datetime.now().isoformat(timespec="seconds")))
        lines = cart_lines(con)
    count = sum(l["qty"] for l in lines)
    what = f"{qty} x " if qty > 1 else ""
    label = f"{item['title']}" + (f" ({variant['title']})" if variant["title"] else "")
    out({"ok": True, "cart": cart_data(lines)},
        f"In the cart: {what}{label} from {item['shop']}. The cart holds {count} item{'s' if count != 1 else ''}.")


def cart_lines(con):
    return [dict(r) for r in con.execute("select * from cart order by shop, id")]


def cart_data(lines):
    by_shop = {}
    for l in lines:
        s = by_shop.setdefault(l["shop"], {"shop": l["shop"], "shop_url": l["shop_url"], "kind": l["kind"],
                                           "currency": l["currency"], "lines": [], "total": 0})
        s["lines"].append(l)
        if l["price"] is not None:
            s["total"] += l["price"] * l["qty"]
    return {"shops": list(by_shop.values()), "count": sum(l["qty"] for l in lines)}


def cmd_cart():
    with db() as con:
        lines = cart_lines(con)
    data = cart_data(lines)
    if not lines:
        out(data, "The cart is empty.")
        return
    text = [f"The cart, {data['count']} item{'s' if data['count'] != 1 else ''}:"]
    for s in data["shops"]:
        text.append(f"{s['shop']}: {money(s['total'], s['currency'])}")
        for l in s["lines"]:
            v = f" ({l['variant']})" if l["variant"] else ""
            text.append(f"  #{l['id']}  {l['qty']} x {l['title']}{v}, {money(l['price'], l['currency'])}")
    out(data, "\n".join(text))


def cmd_qty(args):
    args = [a for a in args if a != "--json"]
    if len(args) < 2 or not args[0].lstrip("#").isdigit() or not args[1].isdigit():
        fail("shopper qty <line> <qty>")
    line, qty = int(args[0].lstrip("#")), int(args[1])
    with db() as con:
        row = con.execute("select * from cart where id = ?", (line,)).fetchone()
        if not row:
            fail(f"There is no line #{line} in the cart.")
        if qty == 0:
            con.execute("delete from cart where id = ?", (line,))
        else:
            con.execute("update cart set qty = ? where id = ?", (qty, line))
        lines = cart_lines(con)
    out({"ok": True, "cart": cart_data(lines)},
        f"{row['title']}: " + ("taken out." if qty == 0 else f"{qty} now."))


def cmd_clear():
    with db() as con:
        con.execute("delete from cart")
    out({"ok": True, "cart": cart_data([])}, "The cart is empty.")


def checkout_links(s):
    """How to order what is in the cart at one shop."""
    root = s["shop_url"]
    if s["kind"] == "shopify":
        parts = ",".join(f"{l['variant_id']}:{l['qty']}" for l in s["lines"] if l["variant_id"])
        return {"checkout": f"{root}/cart/{parts}", "steps": [], "code": "filled",
                "how": "opens the shop's own checkout with everything already in it"}
    if s["kind"] == "woo":
        steps = [{"title": l["title"], "url": f"{root}/?add-to-cart={l['product_id']}&quantity={l['qty']}"}
                 for l in s["lines"]]
        if len(steps) == 1:
            return {"checkout": steps[0]["url"], "steps": [], "code": "cart", "how": "puts it in the shop's cart"}
        return {"checkout": f"{root}/checkout/", "steps": steps, "code": "steps",
                "how": "open each link to put it in the shop's cart, then the checkout"}
    return {"checkout": s["lines"][0]["url"] if len(s["lines"]) == 1 else root,
            "steps": [{"title": l["title"], "url": l["url"]} for l in s["lines"]] if len(s["lines"]) > 1 else [],
            "code": "page", "how": "this shop has no cart link; order it on the product page"}


def cmd_order(args):
    yes = "--yes" in args
    only = " ".join(a for a in args if a not in ("--yes", "--json")).strip().lower()
    with db() as con:
        data = cart_data(cart_lines(con))
        targets = [s for s in data["shops"] if not only or only in s["shop"].lower()]
        if not targets:
            fail("The cart is empty." if not data["shops"] else f"Nothing in the cart from {only}.")
        if not yes:
            text = ["This would be ordered:"]
            for s in targets:
                items = ", ".join(f"{l['qty']} x {l['title']}" + (f" ({l['variant']})" if l["variant"] else "")
                                  for l in s["lines"])
                text.append(f"  {s['shop']}: {items}; {money(s['total'], s['currency'])} plus shipping")
            text.append("Nothing is ordered yet. Ask the owner; on a clear yes run: shopper order --yes"
                        + (f" {only}" if only else ""))
            out({"confirm": True, "shops": targets}, "\n".join(text))
            return
        result = []
        for s in targets:
            links = checkout_links(s)
            con.execute("insert into orders (shop, shop_url, items, total, currency, checkout, created) values (?, ?, ?, ?, ?, ?, ?)",
                        (s["shop"], s["shop_url"], json.dumps([{"title": l["title"], "variant": l["variant"], "qty": l["qty"],
                                                                "price": l["price"], "url": l["url"]} for l in s["lines"]], ensure_ascii=False),
                         s["total"], s["currency"], links["checkout"], datetime.now().isoformat(timespec="seconds")))
            con.execute(f"delete from cart where id in ({','.join('?' * len(s['lines']))})", [l["id"] for l in s["lines"]])
            result.append(dict(links, shop=s["shop"], total=s["total"], currency=s["currency"]))
    text = ["Ready to pay, per shop. Open each link, check the order and pay on the shop's own page:"]
    for r in result:
        text.append(f"  {r['shop']} ({money(r['total'], r['currency'])} plus shipping): {r['how']}")
        for st in r["steps"]:
            text.append(f"    {st['title']}: {st['url']}")
        text.append(f"    {r['checkout']}")
    out({"ordered": result}, "\n".join(text))


def cmd_orders():
    with db() as con:
        rows = [dict(r) for r in con.execute("select * from orders order by id desc limit 20")]
    for r in rows:
        r["items"] = json.loads(r["items"])
    if not rows:
        out({"orders": []}, "Nothing ordered yet.")
        return
    text = ["Ordered before:"]
    for r in rows:
        items = ", ".join(f"{i['qty']} x {i['title']}" + (f" ({i['variant']})" if i.get("variant") else "") for i in r["items"])
        text.append(f"  {r['created'][:10]}  {r['shop']}: {items}, {money(r['total'], r['currency'])}")
    out({"orders": rows}, "\n".join(text))


def cmd_saved():
    with db() as con:
        rows = [dict(r) for r in con.execute("select * from saved order by id desc")]
    if not rows:
        out({"saved": []}, "Nothing kept yet. Say: shopper save <number>.")
        return

    def now_price(r):
        try:
            if r["kind"] == "shopify" and r["handle"]:
                d = fetch_json(f"{r['shop_url']}/products/{r['handle']}.js")
                return d.get("price"), bool(d.get("available"))
            item = from_link(r["url"])
            return item["price"], item["available"]
        except (Stop, OSError, ValueError, KeyError, urllib.error.URLError):
            return None, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fresh = list(pool.map(now_price, rows))
    text = ["Kept to decide later:"]
    with db() as con:
        for r, (price, available) in zip(rows, fresh):
            if price is not None:
                con.execute("update saved set price = ? where id = ?", (price, r["id"]))
                r["price"] = price
            r["available"] = available
            move = ""
            if price is not None and r["first_price"] and price != r["first_price"]:
                diff = price - r["first_price"]
                move = f", {'up' if diff > 0 else 'down'} {money(abs(diff), r['currency'])} since you kept it"
            gone = ", sold out" if available is False else ""
            text.append(f"  #{r['id']}  {r['title']} [{r['shop']}]: {money(r['price'], r['currency'])}{move}{gone}")
    out({"saved": rows}, "\n".join(text))


def cmd_unsave(args):
    args = [a for a in args if a != "--json"]
    if not args or not args[0].lstrip("#").isdigit():
        fail("shopper unsave <id>")
    with db() as con:
        gone = con.execute("delete from saved where id = ?", (int(args[0].lstrip("#")),)).rowcount
    out({"ok": bool(gone)}, "Forgotten." if gone else "There is no such kept product.")


def cmd_shops(args):
    args = [a for a in args if a != "--json"]
    if not args:
        items = [known(s) for s in shops()]
        if not items:
            out({"shops": []}, "You follow no shops yet. Follow one with: shopper shops add <link>.")
            return
        kinds = {"shopify": "searchable", "woo": "searchable", "none": "no open search, add products by link"}
        out({"shops": items}, "Your shops:\n" + "\n".join(
            f"  {s['name']}  {s['url']}  ({kinds.get(s['kind'], 'unknown')}{', ' + s['currency'] if s['currency'] else ''})"
            for s in items))
        return
    if args[0] == "add" and len(args) >= 2:
        url = base_url(args[1])
        name = " ".join(args[2:]).strip() or urllib.parse.urlparse(url).netloc.replace("www.", "").split(".")[0].capitalize()
        if "|" in name or "," in name:
            fail("A shop name cannot hold | or a comma.")
        info = detect(url)
        meta = load(SHOPS_FILE, {})
        meta[url] = info or {"kind": "none", "currency": ""}
        save(SHOPS_FILE, meta)
        current = [s for s in shops() if s["url"] != url and s["name"].lower() != name.lower()]
        store_shops(current + [{"name": name, "url": url}])
        if info:
            out({"ok": True}, f"Following {name}. Its products show up in every search.")
        else:
            out({"ok": True}, f"Following {name}, but it has no open search; add its products by link.")
        return
    if args[0] == "remove" and len(args) >= 2:
        what = " ".join(args[1:]).lower()
        current = shops()
        kept = [s for s in current if what not in (s["name"].lower(), s["url"].lower())]
        if len(kept) == len(current):
            fail(f"You follow no shop called {' '.join(args[1:])}.")
        store_shops(kept)
        out({"ok": True}, f"No longer following {' '.join(args[1:])}.")
        return
    fail("shopper shops, shopper shops add <link> [name], shopper shops remove <name>")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set":
        fail("shopper settings set <shops|per_shop|about> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key == "per_shop":
        if not value.isdigit() or not 1 <= int(value) <= 20:
            fail("Results per shop is a number from 1 to 20.")
        keep(key, value)
        print(f"{value} results per shop.")
    elif key == "shops":
        keep(key, value)
        print(f"{len(shops())} shops.")
    elif key == "about":
        keep(key, value)
        print("Kept. Iris keeps it in mind while shopping." if value else "Cleared.")
    else:
        fail(f"There is no setting called {key}. Use shops, per_shop or about.")


def main(argv):
    argv = [a for a in argv if a != "--json"] if argv and argv[0] == "settings" else argv
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    commands = {
        "search": cmd_search, "results": lambda a: cmd_results(), "show": cmd_show, "add": cmd_add,
        "save": lambda a: cmd_add(a, to_saved=True), "saved": lambda a: cmd_saved(), "unsave": cmd_unsave,
        "cart": lambda a: cmd_cart(), "qty": cmd_qty, "remove": lambda a: cmd_qty(a[:1] + ["0"]),
        "clear": lambda a: cmd_clear(), "order": cmd_order, "orders": lambda a: cmd_orders(),
        "shops": cmd_shops, "settings": cmd_settings,
    }
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
        return
    try:
        if cmd in ("", "--json"):
            cmd_cart() if not load(RESULTS_FILE, {}) else cmd_results()
        elif cmd in commands:
            commands[cmd](rest)
        else:
            cmd_search(argv)
    except Stop as exc:
        if JSON_OUT:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            sys.exit(str(exc))


if __name__ == "__main__":
    main(sys.argv[1:])
