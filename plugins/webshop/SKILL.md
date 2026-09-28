---
name: webshop
description: The owner's own web shop through the webshop plugin, on the house's address (/shop). Products and stock added by voice, orders with their payment status, marking orders paid, sent or cancelled, opening and closing the shop, and payment through the owner's own Mollie key in the vault or a payment request the owner sends.
whenToUse: When the owner wants to start or run a web shop, put a product in the shop or change its price or stock, asks what was ordered or what still has to be sent, says an order is paid or sent, or wants the shop's address. Not for buying things (personal-shopper).
---

# webshop

```sh
webshop                                           # at a glance: to send, waiting for payment, sold this week
webshop add "Mug with a name" 12,50 stock 20 text "Handmade, dishwasher safe"
webshop add "Card" 3 photo https://.../card.jpg
webshop products
webshop edit 1 stock +10                          # or: price 14, name, text, photo
webshop orders                                    # open and paid; also: paid, shipped, all
webshop order 3
webshop paid 3                                    # paid by a payment request the owner sent
webshop shipped 3
webshop cancel 3                                  # stock comes back
webshop close / webshop open
webshop link
webshop mollie ask                                # the owner pastes a Mollie key into the vault
```

- Starting a shop: ask for the shop name, then add the first products, then check `webshop` for what is
  still missing (e-mail, KvK, terms) before the owner shares the link.
- Photos are links (https). Offer to use a photo the owner already has online.
- Without Mollie, tell the owner who to send a payment request and for how much when an order comes in.
- Never mark an order paid unless the owner says the money came in. Never cancel a paid order without
  saying it must be refunded.
- Customer details (names, e-mail, addresses) are the owner's business data: show them to the owner only.
