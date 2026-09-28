# NS trains

Dutch trains live from the **NS**: departures with delays, track changes and cancellations, the next
trips from A to B, and disruptions and works. The command is `trains`.

## What it does

- `trains [station]` - departures, from home unless you name a station
- `trains to <station> [from <station>] [at HH:MM | arrive HH:MM]` - the next trips
- `trains work`, `trains home` - your commute, both ways
- `trains disruptions [station]` - what is disrupted or has works now
- `trains stations <text>` - find a station and its code

A window offers departures, the commute and disruptions as buttons.

## Setup

1. Make a free account at [apiportal.ns.nl](https://apiportal.ns.nl), subscribe to **Ns-App** and copy
   the primary key.
2. Say "connect the NS" (or run `trains key ask`): a safe window opens to paste it into the vault.
3. Set your home and work station under Integrations, or say "my station is Utrecht Centraal".

## How the key is used

The plugin never reads it. Every call is made by the vault with the key filled in as `{g}` in the
`Ocp-Apim-Subscription-Key` header; only the NS answer comes back. The station list is kept for 30 days
in the plugin folder.

## Say to Iris

- "When does the next train to Amsterdam leave?"
- "Is my train to work on time?"
- "How do I get to Den Haag before nine?"

## Permissions

`internet` and `secrets`: to ask the NS with your key from the vault.
