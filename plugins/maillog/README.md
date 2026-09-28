# Maillog

Send transactional mail through your own [Maillog](https://maillog.dev) account and read
what Maillog did with it: recent messages and their delivery status, the API log and the
daily numbers.

The API key lives in the vault. This plugin never sees it, never writes it down and never
prints it: every call goes through `kluis doe maillog-api ...` (or `vault call ...`), so the
value stays on your machine.

## Install and connect

1. Install the plugin from the marketplace, or drop this folder in `~/plugins/maillog`.
2. Store your Maillog key once:

```sh
maillog key ask
```

The vault asks you to paste the key (the one that starts with `ma_`) and keeps it. This is
the only step that needs you. Check it later with `maillog key`.

Create the key in the Maillog dashboard, under API keys. Use a full key so the plugin can
both send and read. A sandbox key works too, but it can only send to the address it was
issued for.

## Commands

```sh
maillog send --to <address> --subject <subject> --body <text> [--from <address>]
maillog send --confirm <id>
maillog events [--limit <n>]
maillog logs [--limit <n>]
maillog stats [--days <n>]
```

`maillog send` does not send anything right away. It prints the message as a draft and
gives you an id. Only `maillog send --confirm <id>` really sends it, within one hour. That
is on purpose: sending reaches another person, so you start it deliberately, once, and see
the exact text first.

The sender is `--from` if you pass it, otherwise the `from` address in `config.json`. Leave
`config.json` empty to always pass `--from`.

`events`, `logs` and `stats` only read. `events` shows recent messages with their delivery
status (the Maillog message list). `logs` shows every API call Maillog handled, newest
first. `stats` shows the daily numbers for the last `n` days (7 by default; the API accepts
7, 30 or 90).

## From the window

Open the plugin and you get a small composer. Fill in the message and press
`Review the message`; the command appears in the conversation, shows the draft and asks you
to confirm. The same screen has buttons for `events`, `stats` and `logs`.

## Endpoints

Everything comes from the [Maillog docs](https://maillog.dev/docs), base URL
`https://api.maillog.dev/v1`:

| Command | Call |
|---|---|
| `send` | `POST /v1/emails` with `from`, `to`, `subject` and `text` |
| `events` | `GET /v1/emails?limit=<n>` |
| `logs` | `GET /v1/logs?limit=<n>` |
| `stats` | `GET /v1/metrics?days=<n>` |

The Authorization header is added by the vault, never by this plugin.

## Errors

Maillog's own errors come back in plain words, without the key:

- `401 unauthorized`: the key is missing or malformed. Put a fresh one in the vault with
  `maillog key ask`.
- `403 forbidden`: the key is invalid, revoked or expired.
- `403 from_not_allowed`: the sender is not on a domain that is verified for sending. Add
  and verify the domain in the Maillog dashboard, or send from a verified address.
- `403 sandbox_restricted`: it is a sandbox key and may only send to its own address.
- `422 validation_error`: a value is wrong; Maillog names the field.
- `429 rate_limited`: too many calls at once. Wait a moment and try again.

## Permissions

- `internet`: to reach `api.maillog.dev`.
- `secrets`: to let the vault make the call with your key.
- `messages`: to put the draft and the answers in the conversation.

## Files

- `maillog.py`: the command. Sending, reading and the draft confirmation.
- `maillog.jsx`: the window with the composer and the read buttons.
- `config.json`: optional default `from` address.
- `lang-nl.json`: the Dutch texts.
- `maillog-api` is the vault item; the key is not in any file here.
