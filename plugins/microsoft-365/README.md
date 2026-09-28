# Microsoft 365

Read Outlook mail, make drafts and send them only after your approval, read the calendar and
make appointments, and read your contacts, through Microsoft Graph.

- Read the inbox, search mail, and read one message with its text.
- Make a draft in Outlook. Nothing is sent until you send that exact stored draft.
- Read the coming appointments and make a new appointment, optionally as an online meeting.
- Read your contacts.
- Everything uses your own Azure app registration. No key or token is shared between homes,
  and there is no central service.

## What you need

1. **An app registration in the Microsoft Entra admin center** at
   [entra.microsoft.com](https://entra.microsoft.com) (App registrations, then New
   registration). Give it any name and choose the account types you need. You do **not** need a
   client secret: this is a public client.
2. Under **Authentication**, add the platform **Mobile and desktop applications** and switch
   **Allow public client flows** to **Yes**. The plugin uses the device code flow, which needs
   this setting and no redirect URL.
3. Under **API permissions**, add these **delegated** permissions, then grant admin consent if
   your organization requires it:
   `User.Read`, `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`,
   `Contacts.Read`, `offline_access`.
   Some organizations only allow an administrator to consent to `Mail.Send`; if the sign-in or
   a command is refused with a 403, ask your administrator.
4. The app's **Application (client) id** goes into the vault. It is not a secret, so `--auto`
   (no fingerprint) is fine:

   ```
   kluis vraag microsoft-365 --domein login.microsoftonline.com --auto "Azure app client id"
   ```

   The plugin never reads the client id. It never runs a call that contains it: the vault makes
   every token request, with the client id filled in as `{g}` inside the vault.

## Setup

1. Start the sign-in:

   ```
   outlook connect
   ```

   It prints a page (`https://microsoft.com/devicelogin`) and a code.

2. Open that page in a browser, sign in with your Microsoft account and approve the app. The
   code is valid for about 15 minutes.

3. Finish the sign-in here:

   ```
   outlook connect --finish
   ```

   The command waits until you approve and then stores the tokens. To start over later, use
   `outlook connect --reset`.

## Commands

```
outlook                                       what is connected, and what still needs a link
outlook connect [--finish] [--reset]          start or finish the sign-in
outlook disconnect                            forget the tokens

outlook mail [--limit n] [--unread] [--folder <name>]
                                              the latest mail (default inbox, 10)
outlook mail read <id>                        one message, with its text
outlook mail search "<query>" [--limit n]     search all mail
outlook mail draft --to <address> --subject "<subject>" --body "<text>"
        [--cc <address>] [--bcc <address>] [--html]
                                              make a draft; nothing is sent
outlook mail send <draft-id>                  send exactly that stored draft
outlook mail drafts                           the drafts waiting for approval

outlook calendar [--days n]                   the coming appointments (default 7)
outlook appointment --subject "<title>" --start <when> [--end <when>]
        [--location "<place>"] [--body "<text>"] [--online] [--all-day]
                                              make an appointment
outlook contacts [--search "<name>"] [--limit n]
                                              your contacts

outlook timezone [<name>]                     show or set the time zone for appointments
```

Add `--dry-run` to `connect`, `mail draft`, `mail send` or `appointment` to see the exact
request that would be made, without calling Microsoft.

`<when>` accepts ISO 8601 (`2026-09-30T14:00`, `2026-09-30 14:00`), `today 14:00`,
`tomorrow 09:30`, `+2h`, `+30m` or a date (`2026-09-30`, which becomes 09:00). Without `--end`
an appointment lasts one hour. The time zone comes from `outlook timezone`, then `TZ`, then the
system.

## Approval before sending

`outlook mail draft` never sends. It makes a real draft in Outlook and stores the exact text
with a short id. `outlook mail send <id>` sends the **stored** text, not whatever is typed
again, so the approved mail and the sent mail are always the same. A draft id is used once; a
second `send` says there is no such draft.

Making an appointment writes to your calendar directly, because that is what you asked the
command to do. Nothing is ever deleted, and no mail is ever sent without `outlook mail send`.

## Where the data lives

- `.state.json` in the plugin folder (mode `600`, readable only by you) holds the access and
  refresh tokens, the time zone and the drafts waiting for approval. Tokens are never printed.
- The app client id lives only in the vault under `microsoft-365` for domain
  `login.microsoftonline.com`.

## Limits and errors

- A `403` usually means a permission is missing or your organization has not consented to it.
  Check step 3 above, or ask your administrator.
- A `401` after a long time means the sign-in expired; run `outlook connect --reset`.
- `outlook connect --finish` reports `authorization_pending` silently while you have not
  approved yet; you can stop it with Ctrl-C and run it again.
- Graph `$search` on mail and contacts cannot be combined with every other option; the plugin
  keeps to what works.
- Without a connected account every read command says so and stops.

## Why the device code flow

The owner's client id stays in the vault, and the plugin never reads it. The device code flow
lets the vault make every token request (the client id is filled in there), so the id never
enters this command, its files or its output. An authorization-code flow with PKCE would need
the client id in the process to build the sign-in URL, which is why it is not used here. The app
registration is still a public client, and no client secret is stored anywhere.
