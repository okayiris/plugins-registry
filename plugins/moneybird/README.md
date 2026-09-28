# Moneybird

Read your Moneybird bookkeeping from the chat. This plugin only **reads**: it never creates,
changes, sends or deletes anything. Every request goes through the vault, so the API token never
enters the plugin, your logs or this repository.

## Commands

```
moneybird                          are we connected, and to which administrations?
moneybird administraties           all administrations
moneybird administratie <id>       one administration in more detail (and remember it)
moneybird contacten [zoek]         contacts, optionally filtered on name/e-mail/city
moneybird facturen [aantal]        the last sales invoices (default 10)
moneybird openstaand               unpaid invoices with the total outstanding
moneybird oauth start [client-id]  the Moneybird authorization link
moneybird oauth koppel <code|url>  exchange an authorization code (through the vault)
moneybird oauth status             is the token in the vault usable?
```

Add `--administratie <id>` to `contacten`, `facturen` or `openstaand` to pick another
administration. `moneybird administratie <id>` remembers the active one in `settings.json`.

## Setup

The plugin needs two things: a public OAuth client id and a token in the vault.

1. Register an application at <https://moneybird.com/user/applications/new>. Moneybird shows a
   client id (public) and a client secret (private). A personal API token on the same page works
   too, and is the simplest route.
2. Save the client id (public) once:

   ```
   moneybird oauth start <client-id>
   ```

3. Put the private parts in the vault. The owner pastes them; the plugin never sees them:

   ```
   kluis vraag moneybird-oauth --domein moneybird.com "Moneybird OAuth client secret"
   kluis vraag moneybird --domein moneybird.com "Moneybird API access token"
   ```

With a personal API token, step 1 and 3b are enough; skip the OAuth dance.

## OAuth flow

Moneybird uses OAuth 2.0 with an out-of-band redirect (`urn:ietf:wg:oauth:2.0:oob`):

1. `moneybird oauth start` prints an authorization URL. Open it as the administration owner.
2. Moneybird shows a code in the browser. Pass it to `moneybird oauth koppel <code>`.
3. The vault performs the token exchange against
   `https://moneybird.com/oauth/token`, so the client secret never leaves the vault. The plugin
   deliberately does **not** print or store the returned token; add the access token to the vault
   with the `kluis vraag moneybird` command above, exactly as the output tells you. A refresh token
   can be kept as an extra `refresh` field on that vault item.

The vault API only lets a plugin *use* a secret (`{g}`), never read or write one. That is why the
last step is a manual paste: keeping the token out of the plugin is the whole point.

## Permissions

- `internet`: talks to `moneybird.com`.
- `secrets`: uses the vault to send the Bearer token, without reading it.

Read-only. Moneybird's OAuth scopes used here are `sales_invoices documents settings`, which cover
administrations, contacts and sales invoices.
