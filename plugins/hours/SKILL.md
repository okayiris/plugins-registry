---
name: hours
description: The owner's time tracking through the hours plugin. A timer to start and stop, hours added afterwards (2,5 or 1:30 or 09:00-12:30), projects with a client and an hourly rate, the day, week and month per project, what is still to invoice, and a CSV export for the bookkeeping.
whenToUse: When the owner starts or stops working on something, says how long they worked on what, asks how many hours they made today, this week or this month, sets up a project or client with a rate, wants to know what to invoice, or wants their hours as a spreadsheet. Not for appointments with others (appointments) or money spent (expenses).
---

# hours

```sh
hours                                         # the timer, today and this week
hours start "Website Bakker" "homepage"       # stops a running timer first
hours start                                   # the last project again
hours stop                                    # or: hours stop at 17:30, when they forgot
hours add 2,5 "Website Bakker" yesterday "meeting"
hours add 09:00-12:30 Intern fri
hours list week                               # the entries with their numbers
hours edit 12 hours 1:45                      # or project, day, note, billable off
hours remove 12
hours week / hours week last / hours month / hours month 2026-09
hours project add "Website Bakker" client "Bakker BV" rate 85
hours project add "Intern" nobill
hours invoice Bakker 2026-09                  # what is still to invoice, with the amount
hours invoice Bakker 2026-09 done             # after the invoice went out
hours export last month                       # a CSV file; add a project to export only that one
```

- A project is its number (#3) or part of its name or client. Hours on a new name make the project; tell
  the owner, so a typo does not become a project unnoticed.
- Lengths: 2,5 and 2.5 are hours, 1:30 is an hour and a half, 90m is minutes, 09:00-12:30 is a span.
- Days: today, yesterday, a weekday (the last one that has been), 2026-09-25 or 25-09. Never one still to come.
- Invoiced hours are fixed: only their note can change. Amounts are before VAT.
- For the invoice itself, the moneybird plugin can make it when the owner uses Moneybird.
