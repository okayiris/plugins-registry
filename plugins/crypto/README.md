# Crypto

Crypto prices for the coins you follow, one coin in detail, and what an amount is worth. Through
[CoinGecko](https://www.coingecko.com)'s public API: no key, no account, and no wallet.

## What it does

- `crypto` - the coins you follow, with the change over 24 hours
- `crypto <coin>` - price, 24 hours, 7 and 30 days, market cap, all-time high
- `crypto <amount> <coin> [currency]` - what an amount is worth
- `crypto add <coin>`, `crypto remove <coin>`

## Setup

Under Integrations: the currency to show prices in (EUR by default) and the coins you follow.

## Say to Iris

- "What's bitcoin doing?"
- "How much is half an ether in dollars?"

## Permissions

`internet`: to ask CoinGecko. Only the coins and the currency are sent. Prices, not advice.
