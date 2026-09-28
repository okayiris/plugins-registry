---
name: checklists
description: Reusable checklists through the checklists plugin, in its own database: packing lists, chores, anything done again and again. Make a list, add items, tick them off, see what is open, reset for next time.
whenToUse: When the owner wants a list they will tick off (packing, chores, preparing something), says they did or packed something on such a list, asks what is still open, or wants a list reset. Not for one-off tasks (todoist) or groceries for meals (meals).
---

# checklists

```sh
checklists                                   # all lists
checklists new Packing
checklists add Packing: passport, charger, sunscreen
checklists check Packing: charger            # a part of the item, or its number
checklists show Packing
checklists reset Packing                     # everything open again
checklists new Weekend from Packing          # a copy
```

- The colon separates the list from the items; commas separate the items.
- Ask before `checklists delete`.
