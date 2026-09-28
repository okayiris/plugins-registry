---
name: recipes
description: Recipes through the recipes plugin (TheMealDB, no key): search by dish, by ingredient or by cuisine, a recipe's ingredients with amounts and its steps, and its ingredients as one grocery line.
whenToUse: When the owner asks what to cook, wants a recipe, asks what they can make with something, or wants the ingredients of a dish on a shopping list.
---

# recipes

```sh
recipes lasagna                # by dish
recipes with chicken           # by ingredient
recipes from italian           # by cuisine
recipes show 2                 # from the last list: ingredients and steps
recipes groceries 2            # one line of ingredients
recipes random
```

- Read the steps one at a time when the owner is cooking, not all at once.
- The recipes are in English with cups and ounces now and then; the units plugin converts.
- For the week's meals and one combined shopping list, `recipes groceries` gives the ingredients to put
  in the meals plugin.
