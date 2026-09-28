# OpenRouter

Use your own OpenRouter account and key for text, images and, when OpenRouter offers it, video.
Every call is an explicit command from you and is paid from your own OpenRouter credit, outside the
Iris credit. There is no central service and no shared key.

## What you need

1. An account at [openrouter.ai](https://openrouter.ai/).
2. Credit or a payment method on that account. OpenRouter charges per token for text and per image
   for images; the price is on each model's page.
3. An API key from [openrouter.ai/keys](https://openrouter.ai/keys/).

The key is only ever used through the vault. This plugin never reads it, never prints it and never
stores it. Each call is a separate command, so nothing runs by itself and nothing is spent without
you asking.

## Setup

Ask for the key once. The vault opens a window, you paste the key there, and it goes straight into the
vault on your Mac:

```
openrouter setup
```

The key is saved under the vault name `openrouter-api` for domain `openrouter.ai`. The first time a
command needs the key, the same window appears if it is not there yet.

To check that it is in place:

```
openrouter
```

## Commands

```
openrouter                          what is set up, and the default models
openrouter models [search]          the models OpenRouter offers (public, no key needed)
openrouter models --all             every text model, up to a limit
openrouter ask "<question>" [--model <id>] [--system "..."]
openrouter image "<prompt>" [--model <id>] [--out NAME]
openrouter video "<prompt>" [--model <id>]
openrouter setup                    paste the API key into the vault, once
openrouter key                      is the key there, and under which vault name
openrouter key item <name> [--domain D]
openrouter default [ask|image|video] [model]
```

Examples:

```
openrouter ask "Explain a solar eclipse in three lines"
openrouter ask "Summarise this" --model anthropic/claude-sonnet-5 --system "Answer in Dutch"
openrouter image "A lighthouse in a storm, watercolour"
openrouter image "A logo for a bakery" --out bakery-logo
openrouter models gemini
```

An image is saved in `~/inbox`, and the command prints the full path. Use `--out NAME` to choose the
file name; without it the name is `openrouter-<date>-<time>`.

`--model` always wins over the default. Without it, the plugin uses the default in `config.json`
(`google/gemini-3.8-flash` for text, `google/gemini-3.1-flash-image` for images). Change a default
without editing code:

```
openrouter default ask openai/gpt-5.4
openrouter default image google/gemini-3-pro-image
```

## Cost

OpenRouter bills your own account: reading the model list is free, but `ask`, `image` and `video`
cost money. The answer shows the model, the token count and, when OpenRouter reports it, the cost of
that call. You can see the balance and set a spending limit in your OpenRouter dashboard.

## Video

OpenRouter has no model that returns video today. `openrouter video` says so plainly instead of
spending anything. If OpenRouter adds one, the command uses the first video model it finds, or the
one you pass with `--model`.

## Where the data lives

- The key lives only in the vault, under `openrouter-api` for domain `openrouter.ai`. The vault makes
  the API call itself, so the key never enters the plugin process.
- `config.json` in the plugin folder holds only the default model names and the vault item name. It
  never holds a key.
- Generated images are written to `~/inbox`. Nothing else is stored.

## Errors

- `401` means the key is wrong or revoked. Put a fresh one in the vault with `openrouter setup`.
- `402` means your OpenRouter credit is too low. Top up in your OpenRouter dashboard.
- `404` means the model id is not known. Find one with `openrouter models <search>`.
- `429` means the rate limit was reached. Try again shortly.

The messages never contain the key. If the vault itself cannot be reached, the plugin says so and
does not try to work around it.
