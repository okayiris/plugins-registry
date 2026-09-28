---
name: appointments
description: The owner's booking page through the appointments plugin, on the house's address (/book). Kinds of appointments with their own length, at a place or by video call (own link or a free meet.jit.si room), webinars with sessions and seats, weekly hours, blocked time, and the bookings people made.
whenToUse: When the owner wants people to be able to book time with them, sets up a kind of appointment or a webinar, says when they can or cannot be booked, asks what is booked today or this week, or wants a booking cancelled or the booking page's address. Not for the owner's own agenda (calendars).
---

# appointments

```sh
appointments                                        # today and what is coming
appointments type add "Introduction" 30 video text "A first talk"
appointments type add "Advice" 60 place "Main Street 1, Utrecht"
appointments type add "Masterclass" 90 webinar seats 20
appointments webinar Masterclass 2026-10-12 19:30   # a session; also: tomorrow, fri
appointments hours "mon-fri 09:00-17:00, sat 10:00-12:00"
appointments block fri 13:00-17:00 "dentist"        # a whole day without times
appointments list today                             # or week, all
appointments show 4
appointments cancel 4
appointments link
```

- Setting up: ask their name (or their business's), the first kind of appointment, and their hours; then
  give them the link.
- Hours are days and times: mon-fri 09:00-17:00; Dutch day names (ma-vr) work too.
- When the owner cancels, tell them to let the guest know by e-mail; the guest's own page shows it too.
- Guests' names and e-mail addresses are the owner's to see, not to share.
