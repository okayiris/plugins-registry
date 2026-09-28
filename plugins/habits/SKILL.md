---
name: habits
description: The owner's small daily habits (walk, read, water, meditate), ticked off by saying so, through the habits plugin. What is open today, the last seven days, streaks. Kept in the house's own database.
whenToUse: When the owner says they did one of their habits, asks what is still open today, how their streak is going, or wants to start or stop keeping a habit.
---

# habits

```sh
habits                       # today: done and still open
habits add walk
habits done walk             # today
habits done walk yesterday   # or a date: habits done walk 2026-09-20
habits undo walk
habits week                  # the last seven days per habit
habits streaks
habits remove walk
```

- "I went for a walk" is `habits done walk` when walk is one of the habits; a part of the name is enough.
- Cheer a new longest streak in one short sentence, no more.
- Ask before `habits remove`: it forgets every tick too.
