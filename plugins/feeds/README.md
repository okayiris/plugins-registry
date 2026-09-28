# Feeds

The news sites and blogs you follow, read from their **RSS** or **Atom** feeds. Iris tells you the
newest items, searches them, and reads out the summary of one.

## What it does

- `feeds` - the newest items of all feeds together
- `feeds latest [name] [count]` - the newest of one feed, or all
- `feeds search <text>` - items whose title or summary mentions it
- `feeds read <number>` - the summary and the link of an item from the last list
- `feeds list`, `feeds add "<name>" <link>`, `feeds remove "<name>"`
- `feeds refresh` - read again now (otherwise feeds are kept for 15 minutes)

## Setup

No account and no key. Add feeds by asking ("follow the NOS news") or under Integrations, one per line
as `Name|link`. A site's own address works too when its page points to its feed.

## Say to Iris

- "What's in the news?"
- "Anything new on the Iris blog?"
- "Is there anything about the elections in my feeds?"

## Permissions

`internet`: to read the feeds you follow. Nothing is sent anywhere else.
