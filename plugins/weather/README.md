# Weather

The weather at home or anywhere else: now and the next hours, the week ahead, and whether it will rain
in the next three hours. Free and keyless, through [Open-Meteo](https://open-meteo.com).

## What it does

- `weather` - now at home: the sky, temperature and how it feels, wind, today's range, sunrise and
  sunset, the next six hours and the air quality
- `weather <place>` - the same anywhere else
- `weather week [place]` - the next seven days
- `weather rain [place]` - rain in the next three hours, per quarter of an hour

A window offers the same three questions as buttons.

## Setup

Nothing to sign up for. Tell Iris where you live ("my home is Utrecht"), or fill in **Home** under
Integrations. The place is looked up once and kept, with its coordinates, in `values.json` in the plugin
folder. Choose metric or imperial units there too.

## Say to Iris

- "What's the weather like?"
- "Do I need an umbrella in the next hour?"
- "What will the weather be in Lisbon this week?"

## Permissions

`internet`: to ask Open-Meteo. Only the coordinates of the place are sent.
