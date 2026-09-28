---
name: todoist
description: The owner's Todoist tasks through the todoist plugin, with their own API token in the vault. Today and overdue, the next seven days, a project, search, adding a task with a date in plain words, and ticking a task off.
whenToUse: When the owner asks what they have to do, what is due, wants something put on their to-do list or Todoist, or says a task is done. Not for appointments (calendars) or quick notes (notes).
---

# todoist

```sh
todoist                                   # today and overdue, numbered
todoist week
todoist add "Call the plumber" tomorrow 9am
todoist add "Pay the dentist" every month on the 1st
todoist done 2                            # a number from the list printed last
todoist done plumber                      # or a part of the task
todoist projects
todoist project work
todoist search dentist
todoist key                               # is there a token
todoist key ask                           # the owner pastes it in the vault
```

- The date words go after the task, in English, as Todoist understands them ("next monday", "every friday").
- Adding and ticking off happen in the owner's own Todoist, for what they asked. Nothing is ever deleted.
- No token yet: tell the owner it is in Todoist under Settings, Integrations, Developer, and run `todoist key ask`.
