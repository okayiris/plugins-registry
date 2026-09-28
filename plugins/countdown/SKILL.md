---
name: countdown
description: How long until the days the owner keeps, through the countdown plugin: trips, deadlines and yearly days such as birthdays and anniversaries. Also days (and working days) until any date.
whenToUse: When the owner asks how long until something, how many days or weeks are left, when a birthday is, or wants a day kept or dropped. Not for appointments at a time of day (calendars).
---

# countdown

```sh
countdown                              # every day kept, the nearest first
countdown add "Holiday Italy" 2026-12-20
countdown add "Anna's birthday" 03-14  # month-day: every year
countdown add "Deadline" 15 Nov 2026
countdown remove "Deadline"
countdown until 2026-12-25             # any date, with the working days in between
```

- A birthday or anniversary is kept without a year, so it comes back every year.
- Past one-off days are shown last, as "was"; offer to drop them.
