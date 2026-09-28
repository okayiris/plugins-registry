# Home Assistant

Read and steer the smart devices in your house through [Home Assistant](https://www.home-assistant.io).
Your Iris can see the states and turn lights, switches, thermostats and speakers on, off or to a value.

## What it does

- `home` - is Home Assistant reachable, how many entities, and how many are active
- `home staten [filter]` - the states, optionally filtered on a name or id
- `home aan <entity>` - turn an entity on
- `home uit <entity>` - turn an entity off
- `home zet <entity> <value>` - set a value: `on`/`off`, a percentage for a light, a temperature for a
  thermostat, a volume for a speaker, or an option for a dropdown

You can use the `entity_id` (`light.keuken`) or the friendly name (`Keukenlamp`); a friendly name is
looked up for you and an ambiguous one is reported back.

## Setup

1. Put your Home Assistant address in `config.json` next to this plugin. It is not a secret:

   ```json
   { "url": "http://homeassistant.local:8123" }
   ```

2. Put a long-lived access token in the vault. In Home Assistant, open your profile (bottom of the
   sidebar), scroll to the bottom and create a long-lived access token. Then run:

   ```sh
   kluis vraag homeassistant --domein homeassistant.local:8123 "Langlevend toegangstoken van Home Assistant"
   ```

   The domain must match the address in `config.json` (without `http://`). The owner pastes the
   token in a secure window; the plugin never sees it.

## How the token is used

The plugin never reads the token. Every request is made by the vault itself, with the token filled in
as `{g}` behind the `Authorization: Bearer` header; only the answer comes back. There is no token in
the code, the config, the README or the logs.

## API

Home Assistant REST API, verified against the current documentation:

- `GET /api/states` - all states
- `GET /api/states/<entity_id>` - one state
- `POST /api/services/<domain>/<service>` with `{"entity_id": "..."}` - call a service

Turning on and off uses the generic `homeassistant.turn_on` / `homeassistant.turn_off` service, which
works for every entity. `home zet` picks a domain-specific service when the value asks for it
(`light.turn_on` with `brightness_pct`, `climate.set_temperature`, `media_player.volume_set`,
`cover.set_cover_position`, `select.select_option`, and so on).
