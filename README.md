# Iris plugins

Plugins for the [Iris marketplace](https://plugins.okayiris.com), built to the
[plugin guide](https://plugins.okayiris.com/docs.md). Each folder under `plugins/` is one flat plugin:
a `plugin.json`, its command, `lang-en.json` (and `lang-nl.json`), a `README.md` for its marketplace
page, a `SKILL.md` telling Iris when to use it, and an icon.

These add to [what is already listed](https://plugins.okayiris.com/llms.txt); no command name clashes
with a listed plugin.

| Plugin | What it does | Permissions |
|---|---|---|
| [weather](plugins/weather) | The weather at home or anywhere: now, the next hours, the week, rain soon, air quality. Open-Meteo, no key. Window. | internet |
| [feeds](plugins/feeds) | The news and blogs you follow, from their RSS or Atom feeds: newest items, search, summaries. Window. | internet |
| [currency](plugins/currency) | Convert money at the ECB's daily reference rates, and see how a rate moved. Frankfurter, no key. | internet |
| [holidays](plugins/holidays) | Public holidays in over a hundred countries, and long weekends with the day off that makes one. Nager.Date, no key. | internet |
| [wikipedia](plugins/wikipedia) | Look things up on Wikipedia in your own language; on this day in history. | internet |
| [notes](plugins/notes) | Quick notes with #tags and pins, in the plugin's own database. Window. | none |
| [habits](plugins/habits) | Daily habits ticked off by saying so, with the week and streaks, in the plugin's own database. Window. | none |
| [worldclock](plugins/worldclock) | The time anywhere, your time elsewhere, and meeting hours across time zones. Offline. | none |
| [expenses](plugins/expenses) | What you spend, said out loud: each month per category, against the month before and your budgets. Own database. Window. | none |
| [countdown](plugins/countdown) | Days until a trip or deadline, and birthdays that come back every year; working days to any date. | none |
| [units](plugins/units) | Convert units in a sentence: length, weight, cooking measures, temperature, speed, area, data, fuel. Offline. | none |
| [crypto](plugins/crypto) | Prices of the coins you follow, one coin in detail, and what an amount is worth. CoinGecko, no key. | internet |
| [books](plugins/books) | A reading list by voice: to read, reading, read, with stars and notes; titles from Open Library. Own database. Window. | internet |
| [todoist](plugins/todoist) | Todoist tasks: today and the week, add a task with a date in plain words, tick one off. Your own token. | internet, secrets |
| [deepl](plugins/deepl) | `translate`: into thirty languages with your own DeepL key, free or Pro, with a polite form. | internet, secrets |
| [personal-shopper](plugins/personal-shopper) | `shopper`: search every shop you like at once, compare on a shopping screen, one cart across shops, and after your yes each shop's checkout opens with everything in it. You pay there. Own database. Screen. | internet |
| [ns](plugins/ns) | `trains`: Dutch trains live, departures with delays and track changes, trips A to B, disruptions. Your own free NS key. Window. | internet, secrets |

Only todoist, deepl and ns need a key of your own. It goes into the vault with `<command> key ask`, and
every call is made by the vault with the key as `{g}`, so the plugin itself never sees it.

## Test

`testenv/` runs plugins as they run in an Iris home, offline and repeatable: commands against recorded
answers, a stand-in vault, a frozen clock, and every window and screen drawn and checked in Chromium.
See [testenv/README.md](testenv/README.md).

```sh
python3 testenv/sim.py test      # scenarios
python3 testenv/sim.py smoke     # nothing crashes
python3 testenv/sim.py screen    # windows and screens, screenshots in testenv/out/
```

## Check and publish

```sh
python3 tools/check.py            # manifest, files, languages, settings and the .jsx design rules
python3 tools/check.py weather    # one plugin
```

Inside an Iris home, copy a folder to `~/plugins/<name>/`, then:

```sh
plugin check weather && plugin enable weather && weather
plugin publish weather
```

Raise `version` in `plugin.json` for every change after a version is published.
