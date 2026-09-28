# Calendar

This house's own calendar, made to sit next to its mailbox. Plan a meeting and the invitation is ready
to mail from the house's own address; an invitation that comes into the mailbox goes into the calendar
with one tap.

- **Plan a meeting** by saying it or in the window: what, when, how long, where and who.
- **With guests, the invitation is written for you**: when and where, and links that put it in Google
  or Outlook, so it works in any mail program. It becomes a mail draft in the house's mailbox, and
  nothing goes out until you press Send.
- **Move or cancel** one of your meetings, and the update or cancellation for the guests is ready the
  same way.
- **Invitations in the mailbox** (an .ics in the mail, as Google, Outlook and Apple send them) are found
  by themselves: put one in the calendar, update it when the organizer changes it, and take it out
  when they cancel it.
- A meeting that overlaps with another one says so.

## What you can say

- "What's on my calendar today?"
- "Plan a meeting with piet@example.com tomorrow at 10 about the kickoff, in room 2."
- "Move the kickoff to Friday at 14:00."
- "Are there invitations in the mail?" / "Put the budget review in my calendar."
- "Cancel the dentist."

## Window

The window shows the next 14 days, a form to plan a meeting (with a date and time picker), and the
invitations in the mailbox. Every button does its own work in the window and shows what it did next to
it. Only **Mail the invitation** hands over to Iris, because a mail from this house is always a draft
that you send yourself.

## With the mailbox

Mailbox and calendar read the same bridge of this house. The `mailbox` window and command show what is
coming up in the calendar and which mails carry an invitation, and a mail with an invitation can be
put in the calendar from there. Either plugin works on its own; together they are one place for your
mail and your day.

## For the curious

```
calendar                                today and tomorrow, and invitations waiting in the mailbox
calendar week [days]                    the days ahead (7 by default)
calendar search <text>                  on title, place, note or guest
calendar show <id>                      one meeting in full
calendar meet "<title>" <date> <time> [--minutes 60] [--with a@x.nl,b@y.nl] [--where <place>] [--note <text>]
calendar move <id> <date> <time> [--minutes N]
calendar cancel <id>
calendar invitation <id>                the invitation again, as a mail draft
calendar invites                        invitations in the mailbox
calendar accept <n|mail id>             put one in the calendar
calendar ics <id>                       the meeting as an .ics file
```

A date is today, tomorrow, a weekday, `next monday`, `2026-10-01` or `1-10`; a time is `14:30` or `14`.
Times are the house's own time. The meetings live in the plugin's own database, in your house.

## Permissions

- `internet`: the calendar reads invitations and the house's address through the mail bridge of this
  house. It never sends a mail itself.
