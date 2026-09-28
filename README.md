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

None of them needs a key or an account.

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
