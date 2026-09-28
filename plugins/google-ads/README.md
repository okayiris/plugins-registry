# Google Ads

Read your Google Ads campaigns, spend and reports from Iris, through the Google Ads API. This plugin
only reads: it never changes a campaign, budget, bid or anything else.

- See the campaigns with their status and budget, and impressions, clicks, costs and conversions.
- See spend by day or by campaign over a chosen period.
- Run any read-only Google Ads Query Language (GAQL) report of your own.

This plugin uses **your own** Google Ads developer token and **your own** OAuth client. Nothing is shared
between homes, and there is no central service.

## What you need

The Google Ads API is heavier to set up than most: it asks for two separate credentials, and the
developer token is only handed out to a Google Ads manager (MCC) account.

1. **A Google Ads manager (MCC) account** with **API access**. In the manager account go to
   **Tools > API Center** (older accounts: **Settings > API Center**), fill in the form and note the
   **developer token**. A brand-new token starts in *test* mode and only works on test accounts; ask
   for **Basic or Standard access** in the same screen to read real accounts. This can take a few days.
2. **A Google Cloud project with the Google Ads API enabled**, from
   [console.cloud.google.com](https://console.cloud.google.com/):
   - Enable the **Google Ads API** under *APIs & Services > Library*.
   - Fill in the **OAuth consent screen** (External is fine; add yourself as a test user).
   - Create an **OAuth client ID** of type **Desktop app** under *APIs & Services > Credentials*.
   - Note the **client ID** and **client secret**. For a Desktop app Google treats the client secret as
     non-confidential, but this plugin still keeps it in the vault, never in a file.
   - The scope used is `https://www.googleapis.com/auth/adwords`.
3. **A Google Ads customer id** for the account you want to read (the ten digits shown in the top right
   of the Google Ads UI). If you read a client account through the manager, you also need the manager's
   customer id as the `login-customer-id`.

## Setup

1. Put the OAuth **client secret** in the vault. A window opens so you can paste it; Iris never sees it:

   ```
   kluis vraag google-ads-oauth --domein googleapis.com "Google Ads OAuth client secret (Desktop app)"
   ```

2. Save your **client id** and **developer token**, and start the login:

   ```
   ads setup --client-id <your-client-id>
   ```

   `ads setup` asks for the developer token with hidden input and stores it in `.state.json` next to the
   plugin (mode `600`). It never prints the token. If you prefer not to have it in a file, export it as
   `GOOGLE_ADS_DEVELOPER_TOKEN` in the environment instead; the plugin uses that first.

3. Finish the Google login:

   ```
   ads login
   ```

   Open the printed link, sign in and allow access. You land on an address that does not load; that is
   expected in this house. Copy the whole address bar and run:

   ```
   ads login --code "<the whole address, or just the code>"
   ```

4. See which customers the login can read, and pick one:

   ```
   ads accounts
   ads customer 1234567890
   ```

   With a manager account, also set its id (sent as the `login-customer-id` header):

   ```
   ads manager 1234567890
   ```

The plugin fails with a clear message and the exact missing piece when any step is not done yet.

## Commands

```
ads                                   what is set up, and what still needs a link
ads setup [--client-id <id>]          one-time: client id, client secret (vault), developer token
ads login                             print the one-time OAuth link
ads login --code <url|code>           finish the login
ads accounts                          the customers this login may read
ads customer <id>                     choose the Google Ads customer
ads manager <id>                      optional manager (MCC) id
ads campaigns [--days N]              campaigns with status, budget and metrics (default 30)
ads costs [--days N] [--by day|campaign]   spend, by day (default) or by campaign
ads report "<GAQL query>"             any read-only GAQL query
ads version [vNN]                     show or set the API version (default v25)
```

Examples:

```
ads campaigns --days 7
ads costs --days 30 --by campaign
ads report "SELECT campaign.name, metrics.cost_micros FROM campaign WHERE segments.date DURING LAST_7_DAYS ORDER BY metrics.cost_micros DESC"
```

## Read-only

`ads report` refuses anything that does not start with `SELECT`. The plugin never calls a
`*:mutate` method, so nothing in your account can change. That is on purpose for this version.

## Where the data lives

- `.state.json` next to the plugin (mode `600`, readable only by the owner) holds the OAuth client id,
  the developer token, the short-lived OAuth tokens and the customer ids. It is a hidden runtime file and
  is **not** part of the published plugin. Delete it to log out and start over.
- The OAuth **client secret** lives only in the vault, under `google-ads-oauth` for the domain
  `googleapis.com`. The token exchange is done by the vault itself, so the secret never reaches the
  plugin and is never printed.

Why the developer token is in `.state.json` and not in the vault: the Google Ads API wants it in a
`developer-token` header on **every** call, next to the OAuth `Authorization` header. The house vault can
substitute only one secret per call, and the Google Ads API does not accept an OAuth token in the query
string. The token is stored with mode `600` and is never printed; the environment variable
`GOOGLE_ADS_DEVELOPER_TOKEN` is used first when it is set.

## Limits and errors

- `DEVELOPER_TOKEN_NOT_APPROVED` or a `403`: your developer token is still in test mode or your account
  has no API access. Ask for Basic or Standard access in the API Center.
- `401`: the OAuth login is no longer valid. Run `ads login` again.
- A `400` on a report is usually a GAQL mistake; the API's message is shown as-is.
- `429`: the API rate limit was reached; try again later.
- Google retires API versions regularly. The plugin pins `v25`; if the API moves on, run
  `ads version v26` (or the version in the [release notes](https://developers.google.com/google-ads/api/docs/release-notes)).
