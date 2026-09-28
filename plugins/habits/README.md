# Habits

Keep small daily habits (a walk, reading, water, stretching) by telling Iris when they are done. She
keeps the ticks and the streaks in the plugin's own database, inside your house.

## What it does

- `habits` - today: what is done and what is still open
- `habits add <name>` - start keeping a habit
- `habits done <name> [yesterday|YYYY-MM-DD]` and `habits undo <name>`
- `habits week` - the last seven days per habit
- `habits streaks` - the current and the longest streak
- `habits remove <name>`

## Say to Iris

- "Start a new habit: read for twenty minutes."
- "I went for a walk."
- "How are my habits going this week?"

## Permissions

None. Everything lives in `data.db` in the plugin's own folder.
