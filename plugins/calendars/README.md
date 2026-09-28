# Calendars

Every calendar you follow in one agenda. Add a Google calendar, a shared family calendar, the school's
holiday list and your Outlook work calendar, and Iris reads them together: what is on today, what the week
looks like, when something is planned with "dentist" in it.

## Adding a calendar

A calendar is a link to an `.ics` file. Where to find it:

- **Google Calendar**: Settings, then pick the calendar, and copy the link under **Secret address in iCal
  format**. One link per calendar, so repeat it for the family calendar and the holidays.
- **Outlook / Office 365**: Settings, Calendar, Shared calendars, Publish a calendar, and take the **ICS**
  link.
- **Apple Calendar**: share the calendar and take the **public calendar** link (a `webcal://` link works too).
- **Nextcloud, Fastmail, Proton**: every one of them has a "link to the calendar" or "export as ICS".

Then say it to Iris, or fill it in yourself:

```
calendars add "Family" https://calendar.google.com/calendar/ical/.../basic.ics
```

The link is a kind of key: it lets anyone read that calendar, so share it with care.

## What you can ask

- "What is on my calendars today?"
- "What does my week look like?"
- "Is there anything with dentist in it the coming months?"
- "Add my work calendar, the link is ..."
- "Drop the football calendar"

Under Integrations the calendars are a list of pills, so you can add and drop one there too, and set how
many days "the week" covers.

## What it costs

Nothing. Reading a calendar link is free.

## For the curious

The command behind it:

```
calendars                      today and tomorrow
calendars week [days]          the days ahead (7 by default)
calendars search <text>        in the next 90 days
calendars feeds                which calendars are added, and how each one reads
calendars add "<name>" <link>  add a calendar
calendars remove "<name>"      drop one
calendars refresh              read the links again now
```

Recurring appointments are worked out from the calendar itself (daily, weekly, monthly and yearly, with an
interval, a count, an end date and the days of the week), and days that are skipped (EXDATE) stay skipped.
A link that cannot be read right now does not spoil the rest: the other calendars still answer, and it says
which one was quiet.
