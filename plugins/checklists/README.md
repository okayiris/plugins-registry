# Checklists

Checklists you use again and again: packing for a trip, the weekly chores, the swimming bag.
Tick things off by saying so, see what is still open, and reset a list to use it the next time. Kept in
the plugin's own database in your house.

## What it does

- `checklists` - every list and how far along it is
- `checklists new <name> [from <list>]` - a new list, empty or a copy
- `checklists add <list>: <item, item>`
- `checklists check <list>: <item or number>`, `checklists uncheck ...`
- `checklists show <list>`, `checklists reset <list>`
- `checklists remove <list>: <item>`, `checklists delete <list>`

## Say to Iris

- "Make a packing list with passport, charger and sunscreen."
- "I packed the charger."
- "What do I still need to pack?"
- "Reset the packing list."

## Permissions

None. The lists live in `data.db` in the plugin's own folder.
