# Meals

Plan the meals of the week and turn them into one grocery list. Everything is kept in
`settings.json` in the plugin folder: no keys, no internet, nothing leaves the house.

## Commands

```
meals                                             the week overview
meals plan <dag> "<gerecht>"                      put a dish on a day
meals weg <dag>                                   clear a day
meals recept "<gerecht>" "<ingredienten>"         save a recipe (comma separated)
meals recept                                      show the known recipes
meals recept weg "<gerecht>"                      forget a recipe
meals boodschappen                                ingredients of the planned dishes, deduplicated
```

- Days may be written out (`maandag`) or short (`ma`, `di`). `vandaag`, `morgen` and `overmorgen`
  also work. `meals plan "<gerecht>"` without a day uses today.
- A recipe is a list of ingredients separated by commas. `meals boodschappen` walks the week in
  order, collects the ingredients of every planned dish and removes doubles. Planned dishes without a
  recipe are named at the bottom so nothing is silently missing.

## Storage

`settings.json` is plain and not secret: `week` maps a day to a dish, `recepten` maps a dish to its
ingredients. Removing the file simply starts over.

## Permissions

None. This plugin only reads and writes its own small file.
