---
name: currency
description: Convert money between currencies at the European Central Bank's daily reference rates, through the currency plugin (Frankfurter, free, no key), and see how a rate moved over days or years.
whenToUse: When the owner asks what an amount is in another currency, what a currency is worth today, or how a rate changed. Not for crypto, stocks or the owner's own bank balance.
---

# currency

```sh
currency 25 USD EUR           # also: currency 25 usd to eur, currency $25
currency 25 USD               # to the owner's own currency
currency rates                # the currencies the owner follows, against their own
currency history USD EUR 90   # how a rate moved
currency settings set home EUR
currency settings set watch "USD, GBP, CHF"
```

- The rates are the ECB reference rates of the last working day, not what a bank or card charges;
  say so when the owner is about to pay.
- About 30 currencies are known (`currency list`). No crypto.
