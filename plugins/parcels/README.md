# Parcels

Track your parcels at **PostNL** and **DHL** and show the latest status per code.

## What it does

- `parcels` - all saved parcels with their latest status
- `parcels add <code> [--vervoerder postnl|dhl]` - save a code (the carrier is guessed from the code)
- `parcels verwijder <code>` - forget a code
- `parcels status <code> [--vervoerder postnl|dhl]` - the latest status of one code

Without a key you get a short explanation of which vault item is missing. Nothing is printed that
could be a secret.

## Setup

1. Codes and carriers are not secret and live in `config.json` next to this plugin:

   ```json
   { "parcels": [ { "code": "3SBOL1234567890", "carrier": "postnl" } ] }
   ```

   You normally do not edit this by hand: `parcels add <code>` writes it for you.

2. Ask the right API key once per carrier. The vault stores it per domain:

   ```sh
   kluis vraag pakketjes --domein api.postnl.nl "PostNL Track & Trace API key"
   kluis vraag pakketjes-dhl --domein api-eu.dhl.com "DHL Shipment Tracking API key"
   ```

   PostNL issues a key through its developer portal. DHL's Shipment Tracking Unified API issues a key
   through the DHL developer portal; there is a public demo key, but it is not stored here.

## How the key is used

The plugin never reads a key. Each lookup is performed by the vault itself, with the key filled in as
`{g}` in the carrier's header (`apikey` for PostNL, `DHL-API-Key` for DHL); only the answer comes back.
There is no key in the code, the config, the README or the logs.

## API

Verified against the current specifications:

- PostNL ShippingStatus V2: `GET https://api.postnl.nl/shipment/v2/status/barcode/{barcode}` with
  header `apikey`. The answer carries `CurrentStatus.Shipment` (`Status.StatusDescription`,
  `DeliveryDate`) and `CompleteStatus.Shipment.Event[]` for the history.
- DHL Shipment Tracking Unified API: `GET https://api-eu.dhl.com/track/shipments?trackingNumber=...`
  with header `DHL-API-Key`. The answer carries `shipments[0].status.description`,
  `estimatedTimeOfDelivery` and `events[]`.

Carrier guessing: `3S...` is PostNL; `JVGL...`, `GM...` or a long number is DHL. When in doubt, pass
`--vervoerder postnl` or `--vervoerder dhl`.
