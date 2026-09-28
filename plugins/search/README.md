# Search

Web search through your own key, with [Brave Search](https://brave.com/search/api/) or
[Google Programmable Search](https://programmablesearchengine.google.com/). The key lives in the
vault, and the vault makes the call: for Brave with the key in the `X-Subscription-Token` header,
for Google in the URL as `{g}`. This plugin never sees it. There is no central service and no
shared key.

## What it does

```sh
search "weather in Groningen"
search "motorcross training tips" -n 10
```

Each result prints the title, the URL and a short description.

## Setup

Pick one provider.

### Brave Search

1. Create an account at [api-dashboard.search.brave.com](https://api-dashboard.search.brave.com/)
   and subscribe to the **Free** plan (2,000 queries a month, one query a second) or a paid plan.
2. Copy the API key from the dashboard.
3. Put it in the vault:

   ```sh
   search key ask brave
   ```

   A window opens where you paste the key. It goes straight into the vault. The item is stored for
   the domain `api.search.brave.com`.

### Google Programmable Search

1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project (or pick an
   existing one) and enable the **Custom Search API** under **APIs & Services > Library**.
2. Under **APIs & Services > Credentials**, choose **Create credentials > API key**.
3. Create a search engine at
   [programmablesearchengine.google.com](https://programmablesearchengine.google.com/), set it to
   search the entire web, and copy the **Search engine ID** (the `cx`).
4. Put the key in the vault and set the engine id:

   ```sh
   search key ask google
   search engine "<your-cx>"
   ```

   The key is stored in the vault for the domain `www.googleapis.com`; the engine id is not a
   secret and is stored next to the plugin in `.state.json`.

## Choosing a provider

If both keys are in the vault, the first one found wins. Set your choice:

```sh
search provider brave
search provider google
search key          # which items are used, never the keys
```

## Notes

- Brave's free plan allows one query a second; space out bursts.
- Google's Custom Search returns at most 10 results per call, so `-n` is capped at 10 for Google
  and 20 for Brave.
- If the key is refused, put a fresh one in the vault with the matching `search key ask`.
