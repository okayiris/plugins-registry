# Google Workspace

Gmail, Google Calendar, Google Contacts and Google Tasks from Iris, with the owner's own Google
Cloud project and OAuth client. Reading is free. Anything that leaves the account or is seen by
others, sending mail and inviting guests, first appears on screen as a draft and waits for a
second command with the exact draft id.

This plugin uses your own Google app and your own credentials. No key or token is shared between
homes, and there is no central service.

## What it does

```
gmail                                       what is set up, and what still needs a link
gmail setup <client-id>                     store the OAuth client id and ask the vault for its secret
gmail connect                               print the consent URL (OAuth 2.0 with PKCE)
gmail connect --code <code|url>             finish the login with the code from the redirect
gmail connect --again                       forget the tokens and start a fresh login
gmail who                                   the connected Google account

gmail mail list [n] [--q "<gmail query>"]   the latest mail, e.g. --q "is:unread newer_than:2d"
gmail mail read <id>                        one message
gmail mail draft <to> "<subject>" "<body>"  a draft in your Gmail, not sent
gmail mail send <to> "<subject>" "<body>"   make a draft; nothing is sent yet
gmail mail send --ja <draft-id>             send that exact draft, only after your yes

gmail cal list [days] [--max n]             what is coming up on the primary calendar
gmail cal add "<title>" <start> [end] [--where ..] [--note ..] [--with a@b,c@d]
gmail cal add --ja <id>                     create an event with guests, only after your yes

gmail contacts list [--max n]               your contacts
gmail contacts search "<text>"              search your contacts

gmail tasks list [--list <id>]              your task lists and open tasks
gmail tasks add "<title>" [--list <id>] [--due 2026-10-01] [--note ..]
gmail tasks done <task-id> [--list <id>]    mark a task completed
```

Times are `2026-10-01T14:00` for a timed event or `2026-10-01` for an all-day event. Events are
created on the primary calendar in that calendar's own time zone.

## What you need

1. **A Google Cloud project** at [console.cloud.google.com](https://console.cloud.google.com/).
2. **These APIs enabled** under *APIs & Services, Library*: Gmail API, Google Calendar API,
   People API and Google Tasks API.
3. **An OAuth consent screen** under *APIs & Services, OAuth consent screen*. Choose *External*
   (or *Internal* for a Workspace account), give it a name, and add your own Google address under
   *Test users* while the app is in testing.
4. **An OAuth client** under *APIs & Services, Credentials, Create credentials, OAuth client ID*.
   Choose application type **Desktop app**. Under *Authorized redirect URIs* add exactly:

   ```
   http://localhost:8765/callback
   ```

   Copy the **client id** and the **client secret**.

The plugin asks for `gmail.readonly`, `gmail.compose`, `gmail.send`, `calendar.readonly`,
`calendar.events`, `contacts.readonly` and `tasks`. It never asks for delete rights on mail.

## Setup

1. Put the client id and secret in the vault. The client secret is never written to a file and the
   plugin never reads it; the client id is kept as the vault item's user name, which is not secret:

   ```
   gmail setup <client-id>
   ```

   This opens the vault window on the owner's device to paste the client secret. The same can be
   done by hand:

   ```
   kluis vraag google-workspace --domein oauth2.googleapis.com --gebruiker <client-id> "Google OAuth client secret"
   ```

2. Start the login:

   ```
   gmail connect
   ```

   Open the printed URL, sign in and approve access. Google shows an unverified-app warning for a
   testing app; continue with *Advanced, Go to ... (unsafe)*.

3. Google sends your browser to `http://localhost:8765/callback`, a page that cannot load here.
   That is expected: copy the whole address bar and finish within a few minutes:

   ```
   gmail connect --code "<paste the whole URL or just the code>"
   ```

The tokens are kept in `.token.json` next to the plugin, readable only by the owner. The client
secret stays in the vault; the token exchange is done by the vault itself.

## Approval before sending and inviting

`gmail mail send "<to>" "<subject>" "<body>"` never sends. It stores a draft and prints it with a
short id. Nothing goes out until `gmail mail send --ja <id>`, and that command sends the **stored**
text, not whatever is passed again, so the approved text and the sent text are always the same.
The same holds for `gmail cal add ... --with ...`: the event and its invitations are only created
by `gmail cal add --ja <id>`. A draft is valid for one hour.

Creating a Gmail draft (`gmail mail draft`), an event without guests and a task or contact change
is done directly.

## Where the data lives

- `.token.json` next to this plugin (mode `600`) holds the Google access and refresh tokens. Tokens
  are never printed.
- `.state.json` (mode `600`) holds the in-progress login state and the drafts that wait for
  approval.
- The client secret lives only in the vault under `google-workspace` for domain
  `oauth2.googleapis.com`. The client id is that item's user name; it is not a secret and appears
  in the consent URL anyway.

## Scopes and permissions

- **internet** - everything goes to `gmail.googleapis.com`, `www.googleapis.com`,
  `people.googleapis.com`, `tasks.googleapis.com`, `oauth2.googleapis.com` and
  `accounts.google.com`.
- **secrets** - it uses a vault item for the client secret, but never reads the value.
- **messages** - it reads and, after approval, sends mail in the owner's name.

## Limits and errors

- A `403 insufficientPermissions` or a mention of a missing scope means the app does not have that
  API or scope; enable the API and run `gmail connect --again`.
- A `401` on every call means the access token is no longer valid. The plugin refreshes it once
  automatically; if there is no refresh token or it expired, run `gmail connect --again`.
- While the OAuth consent screen is in *Testing*, Google expires refresh tokens after seven days.
  Publish the app (or use an *Internal* app) to stop reconnecting every week.
- A `429` means the per-user rate limit for that API was reached; try again later.
- No key, name or account of one owner is baked into the code.
