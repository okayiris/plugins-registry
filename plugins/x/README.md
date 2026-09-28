# X

Manage an X (Twitter) account from Iris, through the X API v2 with OAuth 2.0 and PKCE.

- Read who the connected account is.
- Read the account's latest posts.
- Post a new post.
- Nothing is ever posted without the owner's approval on screen.

This plugin uses your own X app and your own credentials. No key or token is shared between homes,
and there is no central service.

## What you need

1. **An X developer account and app** from [developer.x.com](https://developer.x.com/) (Developer
   Console) with **OAuth 2.0** enabled under User authentication settings.
2. **A paid plan or API credits.** X's API is pay-per-use: you buy API credits in the Developer
   Console, and reads and writes are charged (a post costs per request, a read per resource returned).
   There is no practical free tier for this any more. Without paid access, calls usually fail;
   older limited/free plans were read-only at best, and posting needs paid access.
3. The app type should be a **Native App** (a public client). That is the right type for a desktop or
   CLI plugin: PKCE is used and no client secret is required. If your app is a Web App (confidential),
   X may require a client secret; register a Native App for this plugin instead.
4. Scopes used: `tweet.read`, `users.read`, `tweet.write`, `offline.access`.

## Setup

1. In the X app's **User authentication settings**, add this exact **Callback URL**:

   ```
   http://localhost:8765/callback
   ```

   This house runs in a container, so that localhost address is not reachable from your browser.
   That is fine: X will redirect your browser there, the page will fail to load, and you copy the
   `code` out of the address bar. The plugin documents and uses exactly this redirect so the callback
   registered in the app matches the one sent in the request.

2. Put the app **client secret** in the vault if your app has one (optional for a Native App):

   ```
   kluis vraag x-api --domein x.com "X API client secret"
   ```

   A Native App has no client secret; cancel the window and PKCE still works. The plugin never reads
   the secret and never prints a token.

3. Start the login with your app **client id**:

   ```
   x koppel <client-id>
   ```

4. Open the printed URL, approve access, then copy the whole address bar of the failed localhost page.
   X expires the authorization code quickly (about 30 seconds), so have the next command ready:

   ```
   x koppel --code "<the whole URL, or just the code>"
   ```

## Commands

```
x                        what is connected and what still needs a link
x koppel <client-id>     start the login
x koppel --code <code|url>   finish the login
x koppel --opnieuw       clear the tokens and start a fresh login
x wie                    who the connected account is
x tijdlijn [aantal]      the latest posts (default 5, between 5 and 100)
x post "<text>"          make a draft; nothing is posted
x post --ja <draft-id>   publish that exact draft
```

## Approval before posting

`x post "<text>"` never posts. It stores a draft and prints it with a short id. Nothing goes out until
you run `x post --ja <id>`, and that command posts the **stored** text, not whatever is passed again.
So the approved text and the posted text are always the same.

## Where the data lives

- `.state.json` in the plugin folder (mode `600`, readable only by the owner) holds the client id, the
  access and refresh tokens and the account id. Tokens are never printed.
- The app **secret**, if any, lives only in the vault under `x-api` for domain `x.com`.

## Limits and errors

- X requires `max_results` between 5 and 100 on the timeline endpoint.
- A `403 client-not-enrolled` or a mention of access level means your plan/credits do not include that
  endpoint; posting usually needs paid access.
- A `429` means the rate limit for your plan was reached; try later.
- If the access token expired and there is no refresh token, run `x koppel <client-id>` again.
