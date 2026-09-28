# YouTube

Search and read videos and channels with your own YouTube Data API key, and upload a video with
your own Google OAuth app. Nothing is uploaded before you approve the exact title, description
and privacy on screen. No key or token is shared between homes, and there is no central service.

## Reading

Reading uses a YouTube Data API key that stays in the vault:

```sh
youtube search "motorcross training" -n 5
youtube video https://youtu.be/dQw4w9WgXcQ
youtube channel @mkbhd
youtube channel UCXuqSBlHAE6Xw-yeJA0Tunw
```

`youtube video` shows the channel, duration, views, likes and comments. `youtube channel` shows
the subscriber count and the number of videos.

## Uploading

Uploading uses OAuth with your own Google OAuth client, so the video is published to your own
account. The plugin makes a draft first; only `youtube upload --yes <id>` uploads it.

```sh
youtube upload ~/Videos/rit.mp4 --title "Mijn rit" --description "Vanmiddag" \
  --tags motorcross,rit --privacy unlisted
youtube upload --yes a1b2c3
```

Privacy is `private`, `unlisted` or `public`; the default is `unlisted`. `--category` takes a
YouTube category id (the default, 22, is People & Blogs).

## Setup

### 1. Reading: a YouTube Data API key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a project
   (or pick an existing one).
2. Under **APIs & Services > Library**, enable **YouTube Data API v3**.
3. Under **APIs & Services > Credentials**, choose **Create credentials > API key**.
4. Put the key in the vault:

   ```sh
   youtube key ask
   ```

   A window opens where you paste the key. It goes straight into the vault; this plugin never
   sees it. Check with `youtube key`.

### 2. Uploading: your own Google OAuth client

1. In the same project, open **APIs & Services > OAuth consent screen** and set it up (External
   is fine; add your own Google account as a test user).
2. Under **APIs & Services > Credentials**, choose **Create credentials > OAuth client ID**, type
   **Desktop app**.
3. Add this exact redirect URI to the client:

   ```
   http://localhost:8765/callback
   ```

   This house runs in a container, so that localhost address is not reachable from your browser.
   That is fine: Google will redirect your browser there, the page will fail to load, and you copy
   the `code` out of the address bar.
4. Put the client **secret** in the vault (a Desktop app has one):

   ```sh
   youtube secret ask
   ```

5. Start the login with the client id:

   ```sh
   youtube connect <client-id>
   ```

   Open the printed URL, approve access, then run:

   ```sh
   youtube code "<paste the whole redirect URL>"
   ```

   Check with `youtube who`.

The client secret stays in the vault and is only used by the vault when it exchanges the code.
The OAuth tokens are stored in `.state.json` next to the plugin, readable only by you.

## Notes

- Uploads are checked against the API's daily quota; a single upload is well within it.
- If Google answers `access_denied` during the login, your account is not a test user on the
  OAuth consent screen yet.
- Large files are read into memory before upload. For very large videos, prefer a smaller file or
  upload from YouTube Studio.
