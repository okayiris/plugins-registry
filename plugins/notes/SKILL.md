---
name: notes
description: The owner's own quick notes, kept in the notes plugin's database inside the house. Keep a note, find it again by a word or a #tag, show, change, pin or forget one.
whenToUse: When the owner says to note, jot down, write down or remember something small, or asks what they noted about something. Not for appointments (calendars) or long documents.
---

# notes

```sh
notes                               # the latest notes, pinned first
notes add "Plumber comes Tuesday #house"
notes find plumber
notes find #house
notes show 12
notes edit 12 "Plumber comes Wednesday #house"
notes append 12 "Bring the spare key"
notes pin 12
notes remove 12
notes tags
```

- Keep the owner's own words; add a #tag only when it clearly helps (#work, #house, #gift).
- Ask before `notes remove`: a forgotten note cannot come back.
