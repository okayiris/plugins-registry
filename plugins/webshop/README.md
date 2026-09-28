# Web shop

Start your own web shop in a few sentences. You add products by talking to Iris; your customers order
on your own shop page at `https://<your house>.okayiris.com/shop`; they pay online through your own
**Mollie** account, or you send them a payment request yourself. Stock, orders and shipping are kept in
the plugin's own database in your house.

## What your customers see

A shop page in your house's colours: every product with its photo, price and what is left, a cart,
checking out with name, e-mail and pick-up or delivery, and afterwards a page that shows how their order
stands. At the bottom: your shop name, address, KvK number, contact e-mail and your terms, as a Dutch
web shop has to show.

## What you do

- `webshop` - the shop at a glance: orders to send, what is waiting for payment, what sold this week
- `webshop add "<name>" <price> [stock <n>] [photo <link>] [text "<description>"]`
- `webshop products`, `webshop edit <n> price|stock|name|text|photo <value>`, `webshop hide/show/remove <n>`
- `webshop orders`, `webshop order <id>`, `webshop paid <id>`, `webshop shipped <id>`, `webshop cancel <id>`
- `webshop open` / `webshop close`, `webshop link`

## Payment

- **Mollie** (iDEAL, cards and more): make a Mollie account, then say "connect Mollie" (`webshop mollie
  ask`) and paste your API key; it goes straight into the vault and the plugin never sees it. Customers pay
  on Mollie's page; the payment comes back to the order by itself, and stock comes back when a payment
  expires. Start with a `test_` key to try it without real money.
- **Payment request**: without Mollie an order comes in as waiting for payment. Send the customer a
  payment request (a Tikkie, your bank app) and say "order 3 is paid".

## Stock

An order takes its products from the stock at once, so two customers never buy the last one. Cancelling
an order, or a Mollie payment that expires or fails, puts the stock back.

## Before you share the link

Fill in under Integrations: the shop name, a contact e-mail, your KvK number, your business address and
your delivery and return terms (Dutch law gives customers 14 days to return most things). `webshop` tells
you what is still missing.

## Say to Iris

- "Put a mug in the shop for 12.50, there are 20."
- "What came in today?"
- "Order 3 has been sent."
- "Close the shop for the holidays."

## Privacy and safety

The shop page is public, and shows products only. A customer sees their own order only through the link
with its own secret token. Customer names, e-mail and addresses stay in your house. The house limits
requests per visitor.

## Permissions

`internet` and `secrets`: to create payments at Mollie with your key from the vault. Without Mollie
nothing leaves the house.
