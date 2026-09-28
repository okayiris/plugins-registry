# Currency

Convert money between currencies at the **European Central Bank**'s daily reference rates, and see how
a rate moved. Free and keyless, through [Frankfurter](https://frankfurter.dev).

## What it does

- `currency 25 USD EUR` - convert (also `25 usd to eur`, `$25`, `1.234,56 GBP`)
- `currency 25 USD` - to your own currency
- `currency rates [base]` - today's rates of the currencies you follow
- `currency history USD EUR [days]` - first, last, lowest and highest over a period
- `currency list` - the currencies that are known

## Setup

Nothing to sign up for. Under Integrations you can set your own currency (EUR by default) and the
currencies you follow.

## Say to Iris

- "What is 80 dollars in euros?"
- "How did the pound do against the euro this year?"

## Note

Reference rates are published once every working day around 16:00 CET. What your bank or card charges
is usually a little different.

## Permissions

`internet`: to fetch the rates. Nothing about you is sent.
