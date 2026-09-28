#!/usr/bin/env python3
"""Your own web shop on your house's address: products you add by talking, a shop page for customers,
orders, stock, and payment through your own Mollie account (or a payment request you send yourself).

For the owner:
  webshop                               the shop at a glance: open orders, what came in, the link
  webshop add "<name>" <price> [stock <n>] [photo <link>] [text "<description>"]
  webshop products                      everything in the shop, with stock
  webshop edit <n> <price|stock|name|text|photo> <value>
  webshop hide <n> / webshop show <n>   take a product out of the shop, or back
  webshop remove <n>                    forget a product
  webshop orders [open|paid|shipped|all]
  webshop order <id>                    one order in full
  webshop paid <id>                     the customer paid you another way (a payment request)
  webshop shipped <id>                  sent or picked up
  webshop cancel <id>                   cancel, and the stock comes back
  webshop open / webshop close          take orders, or not (the page says the shop is closed)
  webshop link                          the address of the shop
  webshop mollie / webshop mollie ask   is there a Mollie key in the vault / paste one in
  webshop settings / webshop settings set <key> <value>

For the shop page (the route /shop): the house runs this command with the request as JSON on stdin,
and what it prints is the answer. Actions: catalog, order, status, and Mollie's webhook.

Prices are kept in cents. The Mollie key stays in the vault; every call to Mollie is made by the vault.
"""
import json
import os
import re
import secrets
import select
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.realpath(__file__))
DB_FILE = os.path.join(HERE, "data.db")
SCHEMA_FILE = os.path.join(HERE, "schema.sql")
VALUES_FILE = os.path.join(HERE, "values.json")
ROUTE = "shop"
MOLLIE = "https://api.mollie.com/v2/"
ITEM = "mollie"
DEFAULT = {"name": "", "open": "on", "email": "", "kvk": "", "address": "", "pickup": "on", "shipping": "0",
           "free_from": "", "payments": "request", "terms": "", "currency": "EUR"}
MAX_LINES, MAX_QTY = 30, 99
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- values and database --------------------------------------------------------------------------

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
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(VALUES_FILE + ".tmp", VALUES_FILE)


def db():
    con = sqlite3.connect(DB_FILE, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    if not con.execute("select 1 from sqlite_master where type='table' and name='products'").fetchone():
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            con.executescript(f.read())
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


def cents(text):
    t = str(text).strip().lstrip("€").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
        return None
    return round(float(t) * 100)


def money(c):
    return f"€ {c / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def shipping_for(subtotal, delivery):
    v = values()
    if delivery != "ship":
        return 0
    free_from = cents(v["free_from"]) if v["free_from"] else None
    if free_from is not None and subtotal >= free_from:
        return 0
    return cents(v["shipping"]) or 0


# --- the vault (Mollie) ---------------------------------------------------------------------------

def vault_bin():
    return os.environ.get("KLUIS_BIN") or os.environ.get("VAULT_BIN") or shutil.which("kluis") or shutil.which("vault")


def mollie_item():
    exe = vault_bin()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in r.stdout.splitlines():
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p]
        if len(parts) >= 3 and not line.strip().startswith("de kluis"):
            if parts[0] == ITEM or parts[2].strip().lower().endswith("mollie.com"):
                return parts[0]
    return None


def mollie(method, path, body=None):
    """(status, data) from Mollie, through the vault. (None, reason) when it cannot be asked."""
    item = mollie_item()
    if not item:
        return None, "no Mollie key in the vault"
    cmd = [vault_bin(), "doe", item, method, MOLLIE + path]
    if body is not None:
        cmd += [json.dumps(body), "--kop", "Content-Type: application/json"]
    cmd += ["--kop", "Authorization: Bearer {g}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "Mollie did not answer in time"
    first, _, rest = (r.stdout or "").partition("\n")
    m = re.match(r"status\s+(\d+)", first.strip())
    if not m:
        return None, (r.stderr or r.stdout or "").strip() or "the vault refused the call"
    try:
        return int(m.group(1)), json.loads(rest) if rest.strip() else {}
    except ValueError:
        return int(m.group(1)), {}


def uses_mollie():
    return values()["payments"] == "mollie"


# --- the shop page (route) ------------------------------------------------------------------------

def shop_url(house):
    return f"https://{house}.okayiris.com/{ROUTE}" if house else f"/{ROUTE}"


def catalog():
    v = values()
    with db() as con:
        rows = con.execute("select * from products where visible = 1 order by position, id").fetchall()
    return {
        "shop": {"name": v["name"] or "Web shop", "open": v["open"] == "on", "currency": v["currency"],
                 "pickup": v["pickup"] == "on", "shipping": cents(v["shipping"]) or 0,
                 "free_from": cents(v["free_from"]) if v["free_from"] else None,
                 "email": v["email"], "kvk": v["kvk"], "address": v["address"], "terms": v["terms"],
                 "payments": v["payments"]},
        "products": [{"id": r["id"], "name": r["name"], "price": r["price"], "text": r["text"], "photo": r["photo"],
                      "left": r["stock"], "sold_out": r["stock"] is not None and r["stock"] <= 0} for r in rows],
    }


def clean(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def place_order(body, house):
    v = values()
    if v["open"] != "on":
        return {"error": "closed"}
    customer = body.get("customer") or {}
    name, email = clean(customer.get("name"), 80), clean(customer.get("email"), 120)
    phone, address, note = clean(customer.get("phone"), 30), clean(customer.get("address"), 240), clean(customer.get("note"), 500)
    delivery = "ship" if customer.get("delivery") == "ship" else "pickup"
    if delivery == "pickup" and v["pickup"] != "on":
        delivery = "ship"
    if not name or not EMAIL.match(email):
        return {"error": "customer"}
    if delivery == "ship" and len(address) < 8:
        return {"error": "address"}
    wanted = {}
    for line in (body.get("items") or [])[:MAX_LINES]:
        try:
            pid, qty = int(line.get("id")), int(line.get("qty"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 1 <= qty <= MAX_QTY:
            wanted[pid] = wanted.get(pid, 0) + qty
    if not wanted:
        return {"error": "empty"}
    with db() as con:
        con.execute("begin immediate")          # stock is checked and taken in one go
        lines, subtotal = [], 0
        for pid, qty in wanted.items():
            p = con.execute("select * from products where id = ? and visible = 1", (pid,)).fetchone()
            if not p:
                return {"error": "gone", "id": pid}
            if p["stock"] is not None and p["stock"] < qty:
                return {"error": "stock", "id": pid, "left": max(p["stock"], 0)}
            lines.append((p, qty))
            subtotal += p["price"] * qty
        shipping = shipping_for(subtotal, delivery)
        token = secrets.token_urlsafe(12)
        cur = con.execute(
            "insert into orders (token, status, name, email, phone, address, delivery, note, total, shipping, created, updated) "
            "values (?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (token, name, email, phone, address if delivery == "ship" else "", delivery, note, subtotal + shipping,
             shipping, now(), now()))
        oid = cur.lastrowid
        for p, qty in lines:
            con.execute("insert into lines (order_id, product_id, name, price, qty) values (?, ?, ?, ?, ?)",
                        (oid, p["id"], p["name"], p["price"], qty))
            if p["stock"] is not None:
                con.execute("update products set stock = stock - ? where id = ?", (qty, p["id"]))
    answer = {"order": oid, "token": token, "total": subtotal + shipping, "shipping": shipping, "status": "open"}
    if uses_mollie():
        back = f"{shop_url(house)}?order={oid}&token={token}"
        status, data = mollie("POST", "payments", {
            "amount": {"currency": v["currency"], "value": f"{(subtotal + shipping) / 100:.2f}"},
            "description": f"{v['name'] or 'Order'} #{oid}",
            "redirectUrl": back,
            "webhookUrl": f"{shop_url(house)}/api?hook=mollie",
            "metadata": {"order": oid},
        })
        link = ((data or {}).get("_links") or {}).get("checkout", {}).get("href") if status and status < 300 else None
        if link:
            with db() as con:
                con.execute("update orders set payment_id = ?, pay_url = ?, updated = ? where id = ?",
                            (data.get("id", ""), link, now(), oid))
            answer["pay"] = link
        else:
            answer["pay_error"] = True        # the order stands; the owner sends a payment request
    return answer


def refresh_payment(con, order):
    """Ask Mollie how a payment stands, and follow it: paid, or the stock back when it failed."""
    if order["status"] != "open" or not order["payment_id"]:
        return order["status"]
    status, data = mollie("GET", f"payments/{order['payment_id']}")
    if not status or status >= 300:
        return order["status"]
    state = (data or {}).get("status")
    if state == "paid":
        con.execute("update orders set status = 'paid', updated = ? where id = ?", (now(), order["id"]))
        return "paid"
    if state in ("expired", "canceled", "failed"):
        release(con, order["id"])
        con.execute("update orders set status = 'cancelled', updated = ? where id = ?", (now(), order["id"]))
        return "cancelled"
    return "open"


def release(con, oid):
    for line in con.execute("select * from lines where order_id = ?", (oid,)).fetchall():
        con.execute("update products set stock = stock + ? where id = ? and stock is not null",
                    (line["qty"], line["product_id"]))


def order_status(body):
    try:
        oid = int(body.get("order"))
    except (TypeError, ValueError):
        return {"error": "unknown"}
    with db() as con:
        o = con.execute("select * from orders where id = ?", (oid,)).fetchone()
        # The id alone is not enough: without its own token an order is not there for anyone.
        if not o or not secrets.compare_digest(o["token"], str(body.get("token") or "")):
            return {"error": "unknown"}
        state = refresh_payment(con, o)
        lines = [{"name": l["name"], "qty": l["qty"], "price": l["price"]}
                 for l in con.execute("select * from lines where order_id = ?", (oid,))]
    return {"order": oid, "status": state, "total": o["total"], "shipping": o["shipping"], "lines": lines,
            "delivery": o["delivery"], "pay": o["pay_url"] if state == "open" else ""}


def webhook(body, query):
    """Mollie posts id=tr_... to say a payment changed; ask Mollie itself what it is now."""
    pid = ""
    if isinstance(body, dict):
        pid = str(body.get("id") or "")
    elif isinstance(body, str):
        pid = (urllib.parse.parse_qs(body).get("id") or [""])[0]
    if not re.fullmatch(r"tr_[A-Za-z0-9]+", pid):
        return {"ok": True}
    with db() as con:
        o = con.execute("select * from orders where payment_id = ?", (pid,)).fetchone()
        if o:
            refresh_payment(con, o)
    return {"ok": True}


def api(request):
    body = request.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            pass
    query = request.get("query") or {}
    if query.get("hook") == "mollie":
        return webhook(body, query)
    body = body if isinstance(body, dict) else {}
    action = body.get("action") or query.get("action") or "catalog"
    if action == "catalog":
        return catalog()
    if action == "order" and request.get("method", "POST") == "POST":
        return place_order(body, request.get("house") or "")
    if action == "status":
        return order_status(body or query)
    return {"error": "unknown action"}


# --- the owner ------------------------------------------------------------------------------------

def product(con, ref):
    if not str(ref).lstrip("#").isdigit():
        rows = con.execute("select * from products where lower(name) like ?", (f"%{str(ref).lower()}%",)).fetchall()
        if len(rows) == 1:
            return rows[0]
        sys.exit(f"Several products fit {ref}: " + ", ".join(f"#{r['id']} {r['name']}" for r in rows) + "."
                 if rows else f"There is no product called {ref}.")
    row = con.execute("select * from products where id = ?", (int(str(ref).lstrip("#")),)).fetchone()
    if not row:
        sys.exit(f"There is no product #{ref}.")
    return row


def stock_text(s):
    return "no limit" if s is None else ("sold out" if s <= 0 else f"{s} in stock")


def cmd_overview(house=""):
    v = values()
    with db() as con:
        products = con.execute("select count(*) from products where visible = 1").fetchone()[0]
        open_ = con.execute("select count(*), coalesce(sum(total), 0) from orders where status = 'open'").fetchone()
        paid = con.execute("select count(*), coalesce(sum(total), 0) from orders where status = 'paid'").fetchone()
        week = (datetime.now() - timedelta(days=7)).isoformat()
        sold = con.execute("select coalesce(sum(total), 0) from orders where status in ('paid', 'shipped') and created >= ?",
                           (week,)).fetchone()[0]
        low = con.execute("select name, stock from products where visible = 1 and stock is not null and stock <= 2").fetchall()
    name = v["name"] or "Your shop"
    state = "open" if v["open"] == "on" else "closed"
    print(f"{name} is {state}, with {products} product{'s' if products != 1 else ''} in the shop.")
    if not products:
        print('Add the first with: webshop add "<name>" <price> [stock <n>].')
    if paid[0]:
        print(f"To send: {paid[0]} paid order{'s' if paid[0] != 1 else ''} ({money(paid[1])}). `webshop orders paid`")
    if open_[0]:
        how = "waiting for payment" if uses_mollie() else "waiting for your payment request"
        print(f"{open_[0]} order{'s' if open_[0] != 1 else ''} {how} ({money(open_[1])}).")
    if sold:
        print(f"Sold in the last seven days: {money(sold)}.")
    if low:
        print("Almost gone: " + ", ".join(f"{r['name']} ({stock_text(r['stock'])})" for r in low) + ".")
    missing = [label for key, label in (("name", "a shop name"), ("email", "a contact e-mail"), ("kvk", "your KvK number"),
                                        ("terms", "delivery and return terms")) if not v[key]]
    if missing:
        print("Before you share the shop, add " + ", ".join(missing) + " under Integrations.")


def cmd_add(args):
    if len(args) < 2:
        sys.exit('webshop add "<name>" <price> [stock <n>] [photo <link>] [text "<description>"]')
    name, price = args[0].strip(), cents(args[1])
    if not name or price is None or price <= 0:
        sys.exit(f"{args[1]} is not a price. Like: 12,50.")
    extra, rest = {"stock": None, "photo": "", "text": ""}, args[2:]
    i = 0
    while i < len(rest):
        key = rest[i].lower()
        if key in ("stock", "photo", "text") and i + 1 < len(rest):
            extra[key] = rest[i + 1]
            i += 2
        else:
            sys.exit(f"I did not understand {rest[i]}. Use stock, photo or text.")
    stock = None
    if extra["stock"] is not None:
        if not str(extra["stock"]).isdigit():
            sys.exit("Stock is a whole number.")
        stock = int(extra["stock"])
    if extra["photo"] and not re.match(r"^https://", extra["photo"]):
        sys.exit("A photo is a link that starts with https://.")
    with db() as con:
        pos = con.execute("select coalesce(max(position), 0) + 1 from products").fetchone()[0]
        cur = con.execute("insert into products (name, price, stock, text, photo, position, created) values (?, ?, ?, ?, ?, ?, ?)",
                          (name[:80], price, stock, extra["text"][:600], extra["photo"], pos, now()))
    print(f"#{cur.lastrowid} {name} is in the shop for {money(price)}, {stock_text(stock)}.")


def cmd_products():
    with db() as con:
        rows = con.execute("select * from products order by position, id").fetchall()
    if not rows:
        print('The shop is empty. Add a product with: webshop add "<name>" <price> [stock <n>].')
        return
    print("In the shop:")
    for r in rows:
        hidden = "  (hidden)" if not r["visible"] else ""
        print(f"  #{r['id']}  {r['name']}, {money(r['price'])}, {stock_text(r['stock'])}{hidden}")


def cmd_edit(args):
    if len(args) < 3:
        sys.exit("webshop edit <n> <price|stock|name|text|photo> <value>")
    field, value = args[1].lower(), " ".join(args[2:]).strip()
    with db() as con:
        p = product(con, args[0])
        if field == "price":
            c = cents(value)
            if c is None or c <= 0:
                sys.exit(f"{value} is not a price.")
            con.execute("update products set price = ? where id = ?", (c, p["id"]))
            said = money(c)
        elif field == "stock":
            if value.lower() in ("none", "unlimited", "-"):
                con.execute("update products set stock = null where id = ?", (p["id"],))
                said = "no limit"
            elif value.lstrip("+-").isdigit():
                new = (p["stock"] or 0) + int(value) if value[0] in "+-" else int(value)
                con.execute("update products set stock = ? where id = ?", (max(new, 0), p["id"]))
                said = stock_text(max(new, 0))
            else:
                sys.exit("Stock is a number, like 10 or +5, or unlimited.")
        elif field in ("name", "text", "photo"):
            if field == "photo" and value and not value.startswith("https://"):
                sys.exit("A photo is a link that starts with https://.")
            con.execute(f"update products set {field} = ? where id = ?", (value[:600], p["id"]))
            said = value or "nothing"
        else:
            sys.exit("You can change price, stock, name, text or photo.")
    print(f"{p['name']}: {field} is now {said}.")


def cmd_visible(args, on):
    if not args:
        sys.exit(f"webshop {'show' if on else 'hide'} <n>")
    with db() as con:
        p = product(con, " ".join(args))
        con.execute("update products set visible = ? where id = ?", (1 if on else 0, p["id"]))
    print(f"{p['name']} is {'back in' if on else 'out of'} the shop.")


def cmd_remove(args):
    if not args:
        sys.exit("webshop remove <n>")
    with db() as con:
        p = product(con, " ".join(args))
        con.execute("delete from products where id = ?", (p["id"],))
    print(f"Forgot {p['name']}. Orders that hold it keep it.")


def order_lines(con, oid):
    return con.execute("select * from lines where order_id = ?", (oid,)).fetchall()


def cmd_orders(args):
    which = args[0].lower() if args else "open"
    states = {"open": ("open", "paid"), "paid": ("paid",), "shipped": ("shipped",), "all": ("open", "paid", "shipped", "cancelled"),
              "unpaid": ("open",), "cancelled": ("cancelled",)}.get(which)
    if not states:
        sys.exit("webshop orders [open|paid|shipped|all]")
    with db() as con:
        rows = con.execute(f"select * from orders where status in ({','.join('?' * len(states))}) order by id desc limit 30",
                           states).fetchall()
        if not rows:
            print("No orders to show." if which != "open" else "Nothing waiting: no open or paid orders.")
            return
        labels = {"open": "waiting for payment", "paid": "paid, to send", "shipped": "sent", "cancelled": "cancelled"}
        for o in rows:
            what = ", ".join(f"{l['qty']} x {l['name']}" for l in order_lines(con, o["id"]))
            print(f"  #{o['id']}  {o['created'][:10]}  {o['name']}: {what}; {money(o['total'])}, "
                  f"{'pickup' if o['delivery'] == 'pickup' else 'send'}, {labels[o['status']]}")


def get_order(con, ref):
    if not str(ref).lstrip("#").isdigit():
        sys.exit("Give the order number, like: webshop order 12.")
    o = con.execute("select * from orders where id = ?", (int(str(ref).lstrip("#")),)).fetchone()
    if not o:
        sys.exit(f"There is no order #{ref}.")
    return o


def cmd_order(args):
    if not args:
        sys.exit("webshop order <id>")
    with db() as con:
        o = get_order(con, args[0])
        if o["status"] == "open":
            refresh_payment(con, o)
            o = get_order(con, args[0])
        lines = order_lines(con, o["id"])
    print(f"Order #{o['id']}, {o['created'][:16].replace('T', ' ')}, {o['status']}.")
    for l in lines:
        print(f"  {l['qty']} x {l['name']}  {money(l['price'] * l['qty'])}")
    if o["shipping"]:
        print(f"  shipping  {money(o['shipping'])}")
    print(f"Total {money(o['total'])}.")
    print(f"{o['name']}, {o['email']}" + (f", {o['phone']}" if o["phone"] else ""))
    print("To send to: " + o["address"] if o["delivery"] == "ship" else "Picks it up.")
    if o["note"]:
        print(f"Note: {o['note']}")


def cmd_set_status(args, target):
    if not args:
        sys.exit(f"webshop {target} <id>")
    with db() as con:
        o = get_order(con, args[0])
        if o["status"] == "cancelled":
            sys.exit(f"Order #{o['id']} is cancelled.")
        if target == "cancel":
            if o["status"] == "shipped":
                sys.exit(f"Order #{o['id']} is already sent; handle a return yourself.")
            release(con, o["id"])
            con.execute("update orders set status = 'cancelled', updated = ? where id = ?", (now(), o["id"]))
            refund = " It was paid: refund it in Mollie." if o["status"] == "paid" and o["payment_id"] else (
                " It was paid: pay it back yourself." if o["status"] == "paid" else "")
            print(f"Order #{o['id']} is cancelled and its stock is back.{refund}")
            return
        new = {"paid": "paid", "shipped": "shipped"}[target]
        con.execute("update orders set status = ?, updated = ? where id = ?", (new, now(), o["id"]))
    if target == "paid":
        print(f"Order #{o['id']} of {o['name']} is paid ({money(o['total'])}). Now send it, or have it picked up.")
    else:
        print(f"Order #{o['id']} of {o['name']} is marked as sent. Let {o['email']} know, if you like.")


def cmd_open(on):
    keep("open", "on" if on else "off")
    print("The shop takes orders." if on else "The shop is closed: the page shows the products but takes no orders.")


def cmd_mollie(args):
    if args and args[0] == "ask":
        exe = vault_bin()
        if not exe:
            sys.exit("The vault is not on this system.")
        print("A window opens to paste your Mollie API key (live_... or test_...); it goes straight into the vault.")
        r = subprocess.run([exe, "vraag", ITEM, "--domein", "api.mollie.com", "Mollie API key"],
                           capture_output=True, text=True, timeout=240)
        if r.returncode != 0:
            sys.exit((r.stderr or r.stdout).strip() or "The vault did not save a key.")
        keep("payments", "mollie")
        print("Saved. Customers now pay through Mollie when they order.")
        return
    item = mollie_item()
    if not item:
        print("No Mollie key in the vault. Customers order, and you send them a payment request yourself. "
              "Connect Mollie with: webshop mollie ask.")
        return
    status, data = mollie("GET", "methods")
    if status == 200:
        methods = [m.get("description", m.get("id")) for m in ((data or {}).get("_embedded") or {}).get("methods", [])]
        print(f'Mollie is connected (vault item "{item}"). Customers can pay with: {", ".join(methods) or "no methods yet"}.')
    elif status in (401, 403):
        print("Mollie refused the key. Put a fresh one in the vault with: webshop mollie ask.")
    else:
        print(f"Mollie could not be asked ({data if status is None else 'status ' + str(status)}).")


def cmd_settings(args):
    if not args:
        print(json.dumps(values(), ensure_ascii=False))
        return
    if len(args) < 2 or args[0] != "set" or args[1] not in DEFAULT:
        sys.exit("webshop settings set <" + "|".join(DEFAULT) + "> <value>")
    key, value = args[1], " ".join(args[2:]).strip()
    if key in ("shipping", "free_from") and value and cents(value) is None:
        sys.exit(f"{value} is not an amount.")
    if key in ("open", "pickup") and value not in ("on", "off"):
        sys.exit(f"{key} is on or off.")
    if key == "payments" and value not in ("mollie", "request"):
        sys.exit("Payments are mollie (customers pay online) or request (you send a payment request).")
    if key == "email" and value and not EMAIL.match(value):
        sys.exit(f"{value} is not an e-mail address.")
    keep(key, value)
    print(f"{key}: {value or 'cleared'}.")


def read_request():
    """The request of the shop page, when the house runs this command for the route."""
    if sys.stdin is None or sys.stdin.isatty():
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.5)
    except (OSError, ValueError):
        ready = [sys.stdin]
    if not ready:
        return None
    raw = sys.stdin.read()
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) and "route" in data else None


def main(argv):
    if not argv or argv[0] == "api":
        request = read_request()
        if request is not None:
            print(json.dumps(api(request), ensure_ascii=False))
            return
        if argv:
            sys.exit("webshop api reads the request of the shop page on stdin.")
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    commands = {
        "add": cmd_add, "products": lambda a: cmd_products(), "edit": cmd_edit, "remove": cmd_remove,
        "hide": lambda a: cmd_visible(a, False), "show": lambda a: cmd_visible(a, True),
        "orders": cmd_orders, "order": cmd_order, "paid": lambda a: cmd_set_status(a, "paid"),
        "shipped": lambda a: cmd_set_status(a, "shipped"), "cancel": lambda a: cmd_set_status(a, "cancel"),
        "open": lambda a: cmd_open(True), "close": lambda a: cmd_open(False), "mollie": cmd_mollie,
        "settings": cmd_settings,
        "link": lambda a: print(f"The shop is at {shop_url(os.environ.get('IRIS_HOUSE', '<your house>'))}. "
                                "Share it with whoever you like."),
    }
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        cmd_overview()
    elif cmd in commands:
        commands[cmd](rest)
    else:
        sys.exit("webshop add, webshop products, webshop orders. `webshop help` shows everything.")


if __name__ == "__main__":
    main(sys.argv[1:])
