---
name: calendars
description: Every calendar the owner follows, in one agenda (Google, Outlook, Apple, Nextcloud, school), through the calendars plugin. Today, the week ahead, a search, and calendars simply keep up to date.
whenToUse: When the owner asks what is planned, what their week or day looks like, when something is, whether an appointment exists, or wants a calendar added or dropped. Not for putting something in a calendar (that is the google command, when the house has it).
---

# calendars

The owner's calendars, added by link (an .ics address per calendar). Read them with the `calendars` command:

```sh
calendars                  # today and tomorrow
calendars week 7           # the days ahead
calendars search dentist   # the next 90 days, on title, place or the calendar's name
calendars feeds            # which calendars are added, and how each one reads
calendars add "Family" <link>
calendars remove "Family"
calendars refresh          # read the links again now instead of the copy from up to 30 minutes ago
```

- What it prints is the answer: read it back in your own words, in the owner's language.
- An appointment line ends with the calendar it came from, in brackets, and the place when the calendar has one.
- Adding or dropping a calendar changes what the owner sees under Integrations too: it is the same list.
- A calendar the owner did not add cannot be read. Ask them for the link instead of guessing one.
- Repeating appointments come out of the calendar itself, including skipped days. You never work them out.
- Nothing here writes to a calendar. Planning something goes through `google cal add` in a house with
  Google, where the owner approves it on their screen; without Google, say plainly that this only reads.
