# Test environment

Run plugins as they run in an Iris home, without a house: their commands, their database, their keys,
their windows and screens. Everything is repeatable and works offline.

```sh
python3 testenv/sim.py test                 # every scenario, offline, from the recorded answers
python3 testenv/sim.py test weather -v      # one plugin, showing what each step printed
python3 testenv/sim.py smoke                # all plugins: --help, no arguments, settings; nothing may crash
python3 testenv/sim.py screen               # draw every window and screen; screenshots in testenv/out/
python3 testenv/sim.py screen personal-shopper --images   # with the real product photos (needs internet)
python3 testenv/sim.py serve personal-shopper             # keep it open on a local address to click yourself
python3 testenv/sim.py run weather -- weather Utrecht     # one command in a home that lasts (testenv/.home)
python3 testenv/sim.py run weather --live -- weather Utrecht   # the same, against the real internet
```

`screen` and `serve` install their tools once (`npm install` in `testenv/`). They use the Chromium of
Playwright; set `CHROMIUM_PATH` when yours is somewhere else.

## What a plugin sees

| In a house | Here |
|---|---|
| `~/plugins/<name>/` | a fresh home per scenario, the plugin folder copied in |
| its commands on the path | a wrapper per command that runs the file through its `#!` line |
| `data.db` from `schema.sql` (`database: true`) | made the same way, before the first step |
| the internet | answers from `testenv/cassettes/<plugin>.json` (see below) |
| the vault (`kluis` / `vault`) | `runtime/vault.py`: `lijst`, `vraag`, `doe` and the English `list`, `ask`, `call` |
| the clock | stands still at the scenario's `now` (Monday 28 September 2026, 10:00, Amsterdam) |
| chance | `secrets.token_*` give a fixed series per home, so a request that carries a token can be found in a cassette |
| a route page (`routes` in plugin.json) | served at `/<route>`, with `/<route>/api` running the plugin's command with the request as JSON on stdin, like the house does |
| a window or screen | drawn with `runtime/kit.js`, a stand-in for the kit, with `/commands/run` answered by the plugin's own command |

The stand-in kit is not the real one. It has the same components and props (English and Dutch names),
so it catches crashes, overflow, missing texts and broken buttons, not the exact look.

## Recorded answers

Python's `urllib` is replaced for every command (`runtime/sitecustomize.py`, loaded through
`PYTHONPATH`; the plugins do not change). A request is found back by its method, address and body.

- **replay** (the default): answers come from the cassette. A request that is not in it fails like a
  network error, and the test says which one, so a changed plugin cannot quietly go untested.
- **`--record`**: the real internet, and the answers are added to the cassette. Rate limits (429) and
  server errors are never kept. `--pause 10` waits between steps for services that limit you.
- **`--live`**: the real internet, nothing kept.

The clock stands still, so dates in addresses (a rate history, a forecast) are the same every run.

## Keys

Plugins with a key call the vault, and the vault here answers from the cassette too. The test checks
what the plugin asked: the item, the address, and that the key only ever appears as `{g}`.

To record real answers, give the key in an environment variable named after the vault item. It is used
in the call and never written down; a key that comes back in an answer is replaced by `{g}`.

```sh
IRIS_KEY_TODOIST=... python3 testenv/sim.py test todoist --record
IRIS_KEY_DEEPL=...   python3 testenv/sim.py test deepl --record
IRIS_KEY_NS=...      python3 testenv/sim.py test ns --record
```

Without a key, `--record` uses the plugin's stub in `testenv/stubs/`: sample answers shaped like the
service's documentation. Such a cassette says `"synthetic": true`. The todoist, deepl and ns cassettes
are synthetic until someone records them with a real key.

## A scenario

`testenv/scenarios/<plugin>.json` is a short session: commands in order, in one home, each with what it
should do.

```json
{
  "now": "2026-09-28T10:00:00",
  "vault": ["todoist|api.todoist.com"],
  "stub": "stubs/todoist.py",
  "steps": [
    {"run": "todoist", "expect": {"contains": ["3 tasks for today:"],
                                  "vault": [["GET", "tasks/filter", "Authorization: Bearer {g}"]]}},
    {"run": "todoist done 99", "expect": {"code": 1, "contains": ["not in the last list"]}}
  ],
  "screen": {"lang": "nl", "before": ["todoist"], "actions": [{"click": "text=Vandaag"}, {"said": "todoist"}]}
}
```

A scenario can give the house a program it would have, like the Claude Code CLI (`"programs": {"claude": "stubs/claude.py"}`), and a step can set environment variables (`"env": {...}`). A step can send a request on stdin (`"stdin": {...}`, as a route does) and keep a value from its JSON answer for later steps (`"save": {"token1": "token"}`, used as `${token1}`).

`expect` knows `code` (0 when left out), `contains`, `not_contains`, `matches` (regular expressions),
`lines`, `json` (a path like `items.0.shop` with a value, or `{"min": 2}`, `{"contains": "..."}`,
`{"present": true}`), `vault` (words that one vault call must hold) and `offline_ok` (a missing answer
is expected here, like a service inside the house). A Python traceback always fails a step.

For internet plugins, test the shape of an answer ("°C", "the next seven days"), not today's numbers,
so the scenario still holds after recording again.

`screen` draws the plugin's window (in a narrow tile, a wide tile and on a phone) or screen (desktop and
phone) and fails on a page error, anything wider than its tile, or a text key missing from
lang-en.json. `before` runs commands first; `actions` (for a window or screen) and `routes: {"shop": [...]}` (for a route page) are `click`, `expect`, `gone`, `said` (a sentence
a button gave Iris), `wait` and `shot` (a screenshot). `house` answers other house paths with fixed JSON,
like `"/mail": {...}` for the mailbox.

## Adding a plugin

1. `python3 tools/check.py <plugin>`: the manifest and the design rules.
2. `python3 testenv/sim.py smoke <plugin>`: it runs.
3. Write `testenv/scenarios/<plugin>.json`, then `python3 testenv/sim.py test <plugin> --record` once
   and commit the cassette with it.
4. `python3 testenv/sim.py screen <plugin>` when it has a window or screen, and look at `testenv/out/`.
