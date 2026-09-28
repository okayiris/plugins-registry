---
name: worldclock
description: The time in other places and time zones through the worldclock plugin, offline. The time now somewhere, what a given time is elsewhere, and the hours that fall in working time everywhere for a meeting.
whenToUse: When the owner asks what time it is somewhere, what their time is in another place (or the other way round), how far ahead or behind a place is, or when to plan a call with people in other time zones.
---

# worldclock

```sh
worldclock                        # the owner's places, now
worldclock Tokyo                  # one place
worldclock at 15:00               # 15:00 here, in the owner's places
worldclock at 9am in New York     # 9:00 in New York, here and in the owner's places
worldclock meet London, New York  # hours between 9 and 17 in every place, and here
worldclock add Singapore
worldclock remove Tokyo
```

- A place is a city or a zone (Europe/Paris). A small town: use the nearest big city.
- Daylight saving is taken into account for today; a date far ahead may shift an hour.
