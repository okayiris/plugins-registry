# Travel

Travel time from home to an address. Free and keyless via **OSRM**; optionally with live traffic via
**TomTom**, and with a "when to leave" hint.

## What it does

- `travel` - the home address and which route service is used
- `travel huis "<address>"` - set the home address (looked up once and stored)
- `travel naar "<address>"` - distance and travel time from home
- `travel naar "<address>" --om 14:30` - also say when to leave to arrive at 14:30

The home address is not secret and lives in `config.json` next to this plugin:

```json
{ "home": { "address": "Damrak 1, Amsterdam", "lat": 52.377, "lon": 4.898 } }
```

`travel huis` fills it by itself.

## Route service

- Default: **OSRM** at `https://router.project-osrm.org/route/v1/driving/...` - a free demo server, no
  key, no live traffic. Distance and duration only.
- Optional: **TomTom Routing API** when a key is in the vault. Then the plugin uses TomTom with
  `traffic=true`, which takes current (and, with `--om`, predicted) traffic into account:

  ```sh
  kluis vraag reistijd --domein api.tomtom.com "TomTom Routing API key"
  ```

The plugin never reads the TomTom key. The call is made by the vault itself, with the key filled in as
`{g}` in the URL; only the answer comes back.

## Address lookup

Addresses are looked up with **Photon** (`https://photon.komoot.io/api/`), a free OpenStreetMap
geocoder. Give a city or postcode along with the street for an exact match.

## API

- `GET https://photon.komoot.io/api/?q=...&limit=1` - geocoding
- `GET https://router.project-osrm.org/route/v1/driving/{lon},{lat};{lon},{lat}?overview=false` -
  `routes[0].distance` in metres and `routes[0].duration` in seconds
- `GET https://api.tomtom.com/routing/1/calculateRoute/{lat},{lon}:{lat},{lon}/json?key={g}&traffic=true`
  - `routes[0].summary.travelTimeInSeconds` and `routes[0].summary.lengthInMeters`

With `--om` and a TomTom key the route is asked for the estimated departure time, so the traffic
prediction fits that moment.
