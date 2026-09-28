---
name: calendar
description: This house's own calendar next to its mailbox. Plan meetings with an invitation ready as a mail draft, move or cancel them, and put invitations from the mailbox in the calendar.
whenToUse: When the owner wants to plan, move or cancel a meeting or appointment, asks what is planned, or asks about invitations they got by mail. For calendars followed by link (Google, school, Outlook feeds) use calendars instead.
---

# calendar

The meetings of this house, in the plugin's own database.

```sh
calendar                      # today and tomorrow, and invitations waiting in the mailbox
calendar week 7               # the days ahead
calendar search dentist
calendar meet "Kickoff" tomorrow 10:00 --minutes 60 --with piet@example.com --where "Room 2"
calendar move 3 friday 14:00
calendar cancel 3
calendar invitation 3         # the invitation again
calendar invites              # invitations in the mailbox
calendar accept 1             # put invitation 1 in the calendar
```

- What it prints is the answer: say it back in your own words, in the owner's language.
- **Nothing here sends mail.** `meet`, `move` and `cancel` print the mail for the guests (To, Subject and
  the text). Make exactly that a draft with the house's `mail draft`; the owner presses Send on their
  screen. Do the same when a button asks "Make a mail draft of the invitation for calendar meeting N":
  run `calendar invitation N` and draft what it prints.
- Ask for missing parts before planning: a title, a day and a time. The length is 60 minutes unless
  the owner says otherwise. Guests are mail addresses; when the owner gives a name, ask for the address.
- A meeting from someone else's invitation cannot be moved; the owner answers the organizer by replying
  to their mail (`mailbox read <id>` shows it).
- When it says a meeting overlaps with another, tell the owner before anything goes out.
- Offer `Show my week -> calendar:week` when the owner asks about the days ahead.
