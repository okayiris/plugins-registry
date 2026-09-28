---
name: crypto
description: Crypto prices through the crypto plugin (CoinGecko public API, no key): the coins the owner follows with their 24 hour change, one coin with 7 and 30 day change, market cap and all-time high, and what an amount of a coin is worth.
whenToUse: When the owner asks what bitcoin or another coin is worth, how their coins are doing, or what an amount of a coin is in money. Not for ordinary currencies (currency), stocks, or the owner's own wallet or exchange balance.
---

# crypto

```sh
crypto                        # the coins followed
crypto btc                    # one coin in detail
crypto 0.5 eth                # an amount, in the owner's currency
crypto 0.5 eth usd
crypto add sol
crypto remove sol
crypto settings set currency usd
```

- Report prices, never advice on buying or selling.
- A symbol used by several coins resolves to the biggest one; name the coin in the answer.
