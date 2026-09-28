---
name: personal-shopper
description: The owner's personal shopper through the shopper command. Searches every shop the owner follows at once (Shopify and WooCommerce shops directly, any other shop by product link), shows the products side by side on a screen, keeps a cart across shops, keeps products to decide later with their price now, and gets an order ready at each shop's own checkout after the owner's yes.
whenToUse: When the owner wants to buy, find, compare or order a product, asks what something costs in their shops, wants a shop followed, asks what is in their cart or what they ordered, or pastes a link to a product. Not for groceries planned with meals, and not for paying anything.
---

# personal-shopper (command: shopper)

```sh
shopper settings                              # read "about" first: sizes, colours, budget, brands to avoid
shopper search wool sweater --max 100         # every shop at once; --min, --shop <name> too
plugin open personal-shopper                  # the screen: products side by side, filters, the cart
shopper show 3                                # one product with its sizes and colours
shopper add 3 M                               # into the cart; a size or colour after the number
shopper add 3 10.5 x2                         # two of them; x2 or --qty 2 is the quantity
shopper add https://shop.example/products/x   # a product from any shop, by its link
shopper save 5 / shopper saved                # keep to decide later; saved shows the price now
shopper cart / shopper qty <line> <n> / shopper remove <line>
shopper order                                 # the summary per shop; nothing happens yet
shopper order --yes                           # ONLY after a clear yes from the owner
shopper orders
shopper shops add https://www.allbirds.com Allbirds
```

## How to shop for the owner

1. Read `shopper settings` once: `about` holds their sizes and taste. Use it without asking again.
2. Search with a few plain words, not a sentence ("rain jacket", not "a rain jacket for cycling").
   Put a budget in `--max`. Then open the screen with `plugin open personal-shopper` so they can browse,
   and say in one or two sentences what stands out (cheapest, best fit to their taste, on sale).
3. Adding a Shopify product needs a size or colour when it has several. Take it from `about` when it
   is there; otherwise ask. Never guess a size.
4. Ordering: run `shopper order` and read back the summary per shop with the total. Only after a clear
   yes run `shopper order --yes`, and tell them each shop's checkout is ready: they check it and pay there.
   You never pay, log in or fill in an address; say so if they ask you to.
5. Prices are the shop's own, in the shop's currency, without shipping. Say "plus shipping".

- A shop without open search (most big chains, like Coolblue) still works by link: ask for the link or
  find it with the search plugin, then `shopper add <link>`. bol.com turns such requests away; say so.
- The cart and the orders stay in the house. Only the search words and product pages go to the shops.
