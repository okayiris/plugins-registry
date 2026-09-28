# Appointments

Let people book time with you, on your house's own address: `https://<your house>.okayiris.com/book`.
Make your kinds of appointments by talking to Iris, say when you can be booked, and share the link.
Everything is kept in the plugin's own database in your house. No account and no key.

## Kinds of appointments

- **At a place**: an address people come to, like your studio or office.
- **Video call**: every booking gets its own room on [meet.jit.si](https://meet.jit.si), free and without an
  account, or your own Zoom, Teams or Meet link when you set one.
- **Webinar**: sessions at set moments with a number of seats; everyone in a session shares one video link.

Every kind has its own length and a short description.

## What guests see

A booking page in your house's colours: the kinds of appointments, then a day and a time that are still
free (or a webinar session with its seats left), then their name and e-mail. They get a confirmation with
the address or the video link, a button to put it in their calendar, and a link of their own to come back
to it and cancel.

## What you do

- `appointments` - today and what is coming
- `appointments type add "Introduction" 30 video`, `... "Advice" 60 place "Main Street 1, Utrecht"`,
  `... "Masterclass" 90 webinar seats 20`
- `appointments webinar <type> <date> <time>` - a session of a webinar
- `appointments hours "mon-fri 09:00-17:00, sat 10:00-12:00"` - when you can be booked
- `appointments block <date> [<from>-<to>]` - not available then
- `appointments list [today|week|all]`, `appointments show <id>`, `appointments cancel <id>`
- `appointments open` / `appointments close`, `appointments link`

Under Integrations: your name, how much notice you need (2 hours by default), how far ahead people can
book (30 days), how often a slot starts (every 30 minutes), minutes kept free between appointments, your
own video link and a contact e-mail.

## Never booked twice

A booking checks and takes its moment in one step, and the moment has to be one the page could offer:
inside your hours, with enough notice, not blocked and not taken. A webinar session never takes more
guests than it has seats, and one e-mail address books one seat.

## Say to Iris

- "Make a 30-minute video call type called Introduction."
- "I can be booked on weekdays from nine to five."
- "I am not available on Friday afternoon."
- "Plan the masterclass on 12 October at half past seven."
- "What do I have today?"

## Privacy

The booking page is public and shows only your kinds of appointments and the free moments, never who
booked them. A guest sees their own booking only through the link with its own secret token.

## Permissions

None. Video rooms on meet.jit.si are made by their name alone; nothing is sent anywhere.
