# Socials

Manage a Facebook Page and an Instagram account from Iris, through Meta's Graph API.

- Read the latest Facebook Page posts and Instagram media.
- Publish a Facebook Page post.
- Publish an Instagram image post (container upload, then publish).
- Nothing is ever published without the owner's approval on screen.

This plugin uses your own Meta app and your own credentials. No key, token or account id is shared
between homes, and there is no central service.

## What you need

1. **A Meta app** from [developers.facebook.com](https://developers.facebook.com/) with the product
   **Facebook Login for Business**.
2. **A Facebook Page** that you manage. Reading and posting happen as the Page.
3. For Instagram: an **Instagram Business or Creator account linked to that Facebook Page**.
   A personal Instagram account, or a professional account that is not linked to a Page, cannot be
   managed through this API. The link is made in the Instagram app (`Settings > Account type and tools`)
   or in Meta Business Suite. The plugin says the same thing in a clear error when it is missing.
4. The Meta app must be in **Development mode** with you added as an admin/tester (fine for your own
   use), or have the needed permissions reviewed for use by other people. Requested permissions:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`, `business_management`.

## Setup

The API version is pinned to the current Graph API (`v26.0` at the time of writing).

1. In the Meta app, open **Facebook Login for Business > Settings** and add this exact redirect URI
   under **Valid OAuth Redirect URIs**:

   ```
   https://www.facebook.com/connect/login_success.html
   ```

   That is Facebook's documented redirect for desktop and manual login. This house runs in a container,
   so a `http://localhost` callback of the plugin would never be reachable from your browser. Instead
   the browser ends on Facebook's own success page, which may look empty, and you copy the code out of
   the address bar. That is the redirect this plugin documents and uses.

2. Put the app **secret** in the vault (Iris can use it but never read it):

   ```
   kluis vraag socials-meta --domein facebook.com "Meta app secret for the socials plugin"
   ```

3. Start the login with your app **client id** (public, not a secret):

   ```
   socials koppel <client-id>
   ```

   Open the printed URL, log in, and approve the Page and Instagram permissions.

4. Copy the whole address bar of the page you land on and paste it back (within about ten minutes):

   ```
   socials koppel --code "<the whole URL, or just the code>"
   ```

   The plugin exchanges the code for a short-lived user token, turns it into a long-lived one, and
   reads your Pages. The app secret is used **inside the vault** during that exchange, so it never
   reaches the plugin.

5. If you manage more than one Page, choose the one to use:

   ```
   socials koppel --pagina <page-id>
   ```

## Commands

```
socials                                   what is connected and what still needs a link
socials koppel <client-id>                start the Meta login
socials koppel --code <code|url>          finish the login
socials koppel --pagina <page-id>         choose a Page
socials facebook lijst [--max N]          the latest Page posts
socials facebook post "<text>"            make a draft; nothing is published
socials facebook post --ja <draft-id>     publish that exact draft
socials instagram lijst [--max N]         the latest Instagram media
socials instagram post "<text>" --beeld <public-image-url>   make a draft
socials instagram post --ja <draft-id>    publish that exact draft
```

## Approval before publishing

`... post "<text>"` never publishes. It stores a draft and prints it with a short id. Nothing goes out
until you run the matching `... post --ja <id>`, and that command publishes the **stored** text, not
whatever is passed again. So the approved text and the published text are always the same.
Instagram does not accept text-only posts, so `--beeld` (a publicly reachable image URL) is required.

## Where the data lives

- `.state.json` in the plugin folder (mode `600`, readable only by the owner) holds the client id, the
  OAuth tokens and the selected Page. Tokens are never printed.
- The app **secret** lives only in the vault, under `socials-meta` for domain `facebook.com`.

## Limits and errors

- Instagram allows about 100 API-published posts per 24 hours.
- Publishing needs the Page to have **Page Publishing Authorization** completed if Meta asks for it.
- "Instagram is not linked" means there is no Business/Creator account on the Page; link it first.
- A missing or revoked permission comes back as a Meta error message; `socials facebook lijst` and
  `socials instagram lijst` show the Platform response.
