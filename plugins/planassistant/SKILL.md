---
name: planassistant
description: The owner's day from morning to evening. Morning dashboard with promises on top, meals and breaks kept free, when to leave (with traffic), parking and food at the destination, the children's rides, clashes, what to prepare before a meeting, "how was it?" afterwards, and the evening recap that moves what is left.
whenToUse: When the owner asks how their day looks, what is next, when to leave, where to park or eat near an appointment, about bringing or picking up the children, about overlapping plans, what to prepare, how a meeting went, what they did today, or what moves to tomorrow. Also for the routines below.
---

# planassistant

The day of the owner and their family. The command is `planner`. It reads the house's other plugins
(calendar, calendars, google for appointments; maps or travel for travel time; maps for parking and food;
todoist for tasks) and keeps only its own part: promises, prep, reviews, who is who, rides, the triage.
`planner sources` shows what it found; when a part is missing, offer to install that plugin.

```sh
planner                          # the morning picture: promises, timeline, leave times, prep, clashes, questions
planner next                     # now and the next appointment ("this is your next appointment")
planner leave [--soon]           # when to leave; --soon answers only when it is almost time
planner near c3                  # parking, a quick bite, a place to sit down, near that appointment
planner owner swimming Sem --bring me --pick Lisa    # whose it is and who drives, remembered
planner prep a3 "Print the contract"
planner review a3 --feeling good --outcome "They want a proposal" --action "Write the proposal"
planner promise "Send Piet the photos"     # tomorrow, on top in the morning
planner recap                    # the evening: done, still open
planner move 7 tomorrow          # or overmorrow, nextweek, later, a weekday, a date
planner tomorrow                 # the look ahead, ready for the morning
```

- What it prints is the answer: say it back short and warm, in the owner's language. Never read out
  references like [a3] or #7; use them yourself in the next command.
- **Promises first.** In the morning, start with what the owner promised (it is on top) before the day.
  When the owner says "I'll do that tomorrow" or promises someone something, keep it with `planner promise`.
- **Leaving on time.** When `planner leave --soon` says to leave, tell the owner right away, with the time
  and the travel minutes. When they drive somewhere new, offer to look up parking and food there with `planner near <reference>`.
- **Whose is what.** When the output asks whose a calendar is ("Whose calendar is School?"), ask the owner
  once and run `planner owner "School" Sem` (or `me`, `family`). It is remembered; never ask again.
  A new child or partner: `planner person Sem kid`. Who brings and who picks up goes with `--bring` and
  `--pick` on `planner owner` for a word of the title ("swimming").
- **New appointments** go in the calendar, not the planner: `calendar meet ...` for this house's own, or
  the owner's Google or Outlook calendar.
- **Clashes** are named in the output: tell the owner which two things overlap and for whom, and help
  solve it (move one, or let the partner drive) before anything else.
- **Before a meeting**: when the owner mentions something to finish first, `planner prep <appointment> "..."`.
- **After a meeting**: when `planner next` or the dashboard says an appointment just ended and waits for a
  review, ask briefly "How was <title>?" and keep the answer: `--feeling` one word, `--outcome` a sentence,
  one `--action` per follow-up (they land on tomorrow's list). Which appointments get asked is set with
  `planner evaluate on <word>`.
- **The evening**: run `planner recap`, then go through what is still open one by one: tomorrow, the day
  after, next week or later. Then `planner tomorrow`, and ask whether they promised anyone something.
- A day is today, tomorrow, overmorrow, a weekday, nextweek, later or a date. Settings (how they
  travel, meal times, breaks) are under Integrations, or `planner settings set <key> <value>`.
- The home address lives in travel (`travel huis`) or maps (`maps home`); live traffic comes from maps,
  or from travel with a TomTom key.

## Routines to offer

Suggest these loops once, and set them up after a yes:

- 07:30 on working days: `planner`, told as the morning briefing.
- Every 10 minutes during the day: `planner leave --soon`; speak only when it says to leave.
- Every 30 minutes during the day: `planner next`; when an appointment just ended and waits for a review,
  ask how it went.
- 20:30: `planner recap`, then the look ahead with `planner tomorrow`.

Buttons: `Show my day -> planassistant:today`, `What's next -> planassistant:next`,
`When do I leave -> planassistant:leave`, `Look back on today -> planassistant:recap`,
`Look ahead -> planassistant:tomorrow`.
