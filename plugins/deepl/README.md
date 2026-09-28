# DeepL

Translate text into more than thirty languages with your own [DeepL](https://www.deepl.com/pro-api)
key, free or Pro. The command is `translate`.

## What it does

- `translate <text>` - into your usual language; the source language is detected
- `translate to <language> <text>` - into any other, by name or code
- `translate formal to <language> <text>` - the polite form (u, Sie, vous) where there is one
- `translate usage` - characters used this month
- `translate languages`

## Setup

1. Make a DeepL API account (the free plan translates 500,000 characters a month) and copy the key
   under Account, API keys.
2. Say "connect DeepL" (or run `translate key ask`): a safe window opens to paste it into the vault.

Free keys use `api-free.deepl.com` and Pro keys `api.deepl.com`; the plugin finds out which by itself.

## How the key is used

The plugin never reads it. Every call is made by the vault with the key filled in as `{g}` in the
`Authorization: DeepL-Auth-Key` header; only DeepL's answer comes back.

## Say to Iris

- "Translate this into German: see you on Monday."
- "What does 'Wir freuen uns auf Sie' mean?"

## Permissions

`internet` and `secrets`: the text you translate goes to DeepL, with your key from the vault.
