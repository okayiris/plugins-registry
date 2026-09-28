# Maps

Routes, travel time and places through your own Google Maps API key. The key never enters the
plugin: it lives in the vault, and the vault itself makes the call with the key filled in as
`{g}`. Only the answer comes back.

## What it does

```sh
maps route "Groningen"
maps route "Zevenhuizen" "Amsterdam"
maps route "home" "Schiphol" --mode transit
maps find "koffie" --near "Groningen" -n 5
maps geocode "Carolieweg 22, Zevenhuizen"
maps home "Carolieweg 22, Zevenhuizen"
```

`maps route` takes one address (from home) or two, and prints the distance, the travel time and,
for driving and transit, the time with live traffic. `maps find` searches places and shows the
address, rating and whether they are open now. `maps geocode` turns an address into coordinates.

## Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a project (or
   pick an existing one). Billing has to be enabled; Google gives a monthly credit for Maps, but
   without billing the APIs stay off.
2. Under **APIs & Services > Library**, enable these three APIs:
   - **Geocoding API**
   - **Directions API**
   - **Places API**
3. Under **APIs & Services > Credentials**, choose **Create credentials > API key**. Optionally
   restrict the key: under **API restrictions**, pick only the three APIs above.
4. Put the key in the vault:

   ```sh
   maps key ask
   ```

   A window opens where you paste the key. It goes straight into the vault; neither this plugin
   nor Iris ever sees it. The item is stored for the domain `maps.googleapis.com`.
5. Check with `maps` and try a route.

There is no central service and no shared key: every home uses its own Google app and its own key.

## Notes

- Travel times use the Google Directions API. Live traffic needs the `departure_time` query,
  which this plugin always sends for driving and transit.
- If Google answers `REQUEST_DENIED`, the key is missing an enabled API or a billing account.
- `maps home` stores a plain address in `config.json` next to the plugin; it is not a secret.
