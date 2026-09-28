# Stripe

See your own Stripe balance, payments, customers, invoices, subscriptions and monthly
revenue from Iris, with your own Stripe key. Version 1.0.0 is deliberately **read-only**:
it never creates, changes, refunds or deletes anything.

Everything runs against `https://api.stripe.com` with GET requests only, through a key that
stays in the vault. This plugin never sees the key and never writes it to a file or a log.

## What it does

```sh
stripe balance
stripe payments [--limit <n>]
stripe customers [--search <term>] [--limit <n>]
stripe invoices [--status <status>] [--limit <n>]
stripe subscriptions [--status <status>] [--limit <n>]
stripe revenue [--month <YYYY-MM>]
stripe key
stripe key ask
stripe key item <name> [--domain <domain>]
```

Examples:

```sh
stripe balance
stripe payments --limit 25
stripe customers --search "jane"
stripe invoices --status open
stripe subscriptions --status active
stripe revenue --month 2026-09
```

- `payments` lists the latest charges with date, amount, status and who paid.
- `customers --search` searches both name and email.
- `invoices --status` accepts `draft`, `open`, `paid`, `uncollectible` or `void`.
- `subscriptions --status` accepts `active`, `past_due`, `unpaid`, `canceled`,
  `incomplete`, `incomplete_expired`, `trialing` or `all`. Without `--status`, Stripe
  leaves out canceled subscriptions.
- `revenue` sums the successful payments of a calendar month in UTC, per currency, and
  shows gross, refunded and net. Without `--month` it uses the current month.

Amounts are printed with the currency and the right number of decimals, for example
`EUR 1,234.56` or `JPY 1,234`. Stripe sends amounts in the smallest unit, so
`EUR 1234` is one thousand two hundred thirty four euro.

## The window

Next to the commands there is a small window in the house kit (open it with the app card or
`plugin open stripe`). It shows what the plugin may read and runs the same commands with a
tap: balance, revenue, payments, customers, invoices and subscriptions. The window only
launches a command; the numbers themselves always come back in the conversation.

## The key

Use a **restricted key** with read-only permissions. In the Stripe Dashboard open
**Developers**, then **API keys**, then **Create restricted key**, and give it **read**
access to:

- Balance
- Charges (payments and revenue)
- Customers (also used by the search)
- Invoices
- Subscriptions

Leave every write permission off. A restricted key starts with `rk_live_` or `rk_test_`.
Do not use a full secret key (`sk_`): this plugin needs no write access, so it should
never hold one.

Ask for the key once, in a safe window on the owner's machine:

```sh
kluis vraag stripe-api --domein stripe.com "Stripe restricted API key (read-only)"
```

The vault binds the item to `stripe.com` and makes every call itself, with the key filled
in as `{g}`. Only Stripe's answer comes back to the plugin. Check the connection with:

```sh
stripe key
```

Point it at another vault item or domain with:

```sh
stripe key item my-stripe --domain stripe.com
```

A test key and a live key see different data. `stripe balance` prints whether it is in
`live` or `test` mode.

## Errors

Errors from Stripe come back in plain words, and the key is never printed:

- **401**: the key was refused. It may be wrong or revoked, or it may be for the other
  mode (test versus live).
- **403**: the restricted key has no read permission for that resource. Add the read
  permission in the Stripe Dashboard and try again.
- **429**: Stripe's rate limit was reached. Try again in a moment.
- Anything else: Stripe's own message, shortened.

## Read-only, for now

Version 1.0.0 only reads. Creating a payment, sending an invoice or issuing a refund is
not built yet: writing touches real money, so it will be added as a later version and
only after it is asked for and approved separately.

## Permissions

- **internet**: every request goes to `api.stripe.com`.
- **secrets**: it uses a vault item, but never reads the value.

## Notes

- Nothing of yours is stored. The only file next to this plugin is `config.json`, which
  holds the vault item name and domain, and never the key itself.
- The plugin refuses any URL outside `api.stripe.com`.
