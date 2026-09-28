# Spotify

See what is playing on Spotify, search tracks, and play, pause or skip. Playing, pausing and skipping
need **Spotify Premium** and an active Spotify device (open Spotify on a phone, computer or speaker).

## What it does

- `spotify` - is Spotify linked, and what is playing now
- `spotify nu` - the current track, with progress and where it plays
- `spotify zoek "<text>"` - search tracks and show their `spotify:track:...` uri
- `spotify speel [uri]` - resume, or play a track, album or playlist uri
- `spotify pauze` - pause
- `spotify volgende` / `spotify vorige` - skip
- `spotify login` - print the one-time login link; `spotify login "<url>"` finishes it

Without a link you get a short explanation of what is missing and how to add it.

## Setup

1. Create an app on the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
2. Add this **Redirect URI** to the app:

   ```
   http://127.0.0.1:8888/callback
   ```

   This works in this house: after you approve, the browser lands on that address and cannot load a
   page, but the address bar holds the `code`. You copy the whole address bar. Spotify allows plain
   `http` only for a loopback address like `127.0.0.1`, which is why it is not a public URL.
3. Copy the app's **Client ID** and **Client Secret**. Put the Client ID in `config.json` next to
   this plugin (it is not a secret):

   ```json
   { "client_id": "your-client-id", "redirect_uri": "http://127.0.0.1:8888/callback" }
   ```

   and let the vault hold the Client Secret. You can also store the Client ID as the vault user:

   ```sh
   kluis vraag spotify --domein accounts.spotify.com --gebruiker <client-id> "Spotify client secret"
   ```

4. Log in once:

   ```sh
   spotify login
   ```

   Open the link, approve, copy the whole address you land on, and run:

   ```sh
   spotify login "<the whole address>"
   ```

Search uses the app-only (Client Credentials) token. Player control uses the user login from step 4.

## How the secret is used

The plugin never reads the Client Secret. Every token exchange is performed by the vault itself, with
the secret filled in as `{g}` in the request body; the vault normally returns only the answer. The
short-lived access token from that answer is used for the API calls and is never printed. The login in
step 4 is kept in `.token.json` next to this plugin, readable only by the owner (`chmod 600`); it is a
hidden runtime file and is not part of a published plugin. Delete it to log out.

## API

Spotify Web API, verified against the current documentation:

- `GET /v1/me/player` - the player and current track
- `PUT /v1/me/player/play` - resume or play `{"uris": [...]}`
- `PUT /v1/me/player/pause`
- `POST /v1/me/player/next` and `POST /v1/me/player/previous`
- `GET /v1/search?type=track&q=...`
- `POST https://accounts.spotify.com/api/token` - Client Credentials, Authorization Code and refresh

Scopes used: `user-read-playback-state`, `user-modify-playback-state`, `user-read-currently-playing`.
