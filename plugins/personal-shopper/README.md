# Personal shopper

Your own personal shopper. Iris searches every shop you like at once and puts the products side by
side on one screen: filter per shop, sort by price, only what is in stock. Keep one cart across all
those shops, keep products to decide later (with their price now), and when you say yes, Iris gets the
order ready at each shop's own checkout. You check it and pay there.

## What it does

- **Search every shop at once**: `shopper search <what> [--max 100]`
- **A shopping screen** (`plugin open personal-shopper`): product tiles with photo, price, sale price
  and stock; filter per shop, sort cheapest or priciest; pick a size right on the tile
- **One cart across shops**: totals per shop, change amounts, take things out
- **Keep for later**: see whether the price went up or down since you kept it
- **Order after your yes**: per shop one link to its own checkout with everything already in it
- **Order history**

## Which shops

- **Shopify shops** (a large share of web shops, like Allbirds): searched directly, with sizes and
  colours, and the order opens their checkout already filled in.
- **WooCommerce shops**: searched directly; the order puts the products in the shop's cart.
- **Any other shop**: paste a product link. Iris reads the product, price and stock from the page, and
  the order opens that product page. Some big shops (bol.com) turn such requests away.

Follow a shop by saying "follow allbirds.com as a shop", or under Integrations as `Name|link`.

## What Iris never does

She never pays, never logs in to a shop, and never sees a password, card or address. Nothing is
ordered without your yes, and even then the paying happens on the shop's own page.

## Setup

Under Integrations: your shops, how many results per shop, and **What Iris should know**: your sizes,
colours you like, brands you avoid, a budget.

## Say to Iris

- "Find me a warm wool sweater under 100 euro."
- "Put the grey one in size M in my cart."
- "Keep those sneakers, I'll decide later."
- "Order my cart."

## Permissions

`internet`: to search the shops and read product pages. The cart, what you kept and what you ordered
stay in the plugin's own database in your house.
