# Plan assistant

Your day from morning to evening, with the family and the road in it. Iris starts the day with a clear
picture, keeps you on time, asks how your meetings went, and closes the day with you, so tomorrow is
ready before you wake up.

The plan assistant does not keep a second agenda. It reads the plugins you already have and adds what
none of them does: promises, what to prepare, who brings and picks up the children, meals and breaks,
clashes, "how was it?" and the evening triage.

| For | It uses | Without it |
|---|---|---|
| Appointments | **calendar** (this house's own), **calendars** (.ics links), **google** (Google Calendar) | only your tasks and promises |
| Travel time | **maps** (Google, with traffic, from anywhere), else **travel** (free, from home) | no time to leave |
| Parking and food | **maps** | not available |
| Tasks | **todoist**, next to the planner's own | the planner's own tasks |

`planner sources` says what it found in your house.

## Morning

- **The day at a glance**: one screen with today's timeline, from the first appointment to dinner.
- **Promises first**: what you promised yesterday to do today is on top of the list.
- **Meals and rest**: lunch, dinner and a break after a long busy stretch are kept free by themselves,
  in the nearest gap when your day is full. A day without room for lunch says so.

## On the road and with the family

- **When to leave**: through maps (with traffic, also from your previous appointment) or travel (from
  home, with traffic when it has a TomTom key). Iris tells you when it is time.
- **Parking and a bite**: through maps, the nearest parking, a quick coffee and a place to sit down
  around the address of your appointment, with ratings and whether they are open.
- **The children**: swimming, sports, school and hobbies stay in your calendars. Tell the planner once
  whose they are and who brings and picks up; the rides land in the right person's day.
- **Clashes**: two things at once for you, a child with two activities, one driver in two places, and
  the same appointment in two calendars. Not sure whose calendar is whose? Iris asks once and remembers.

## Before, during and after a meeting

- **Prepare**: what has to be finished before an appointment, shown with it.
- **Straight to the next one**: when an appointment ends, the window shows "This is your next
  appointment", with the time to leave.
- **How was it?**: after the appointments you choose (like every "client" meeting), Iris asks briefly
  how it went and keeps the feeling, the outcome and the follow-ups. Follow-ups land on tomorrow's list.

## Evening

- **Looking back**: what you did and finished today, and which promises you kept.
- **What is left**: each open task goes to tomorrow, the day after, next week or later, in one tap.
- **Looking ahead**: tomorrow's first appointment and when to leave, your promises and tasks, ready for
  the morning.

## What you can say

- "How does my day look?" / "What's next?"
- "When do I need to leave for the dentist?" / "Where can I park near the client?"
- "Swimming is Sem's; I bring him, Lisa picks him up."
- "I promised Piet the photos tomorrow."
- "Before the kickoff I need to finish the slides."
- "The meeting went well, they want a proposal."
- "Let's close the day." / "Move the holiday booking to next week."

## Window

Today's picture: now and your next appointment with the time to leave, your promises, clashes and
questions, the timeline with meals and breaks, and your tasks with a Done button. After five in the
evening (or with **Evening**) it turns into the recap, where every open task moves with one tap.

## Settings

Under Integrations: how you travel, how early you want to be somewhere, when your day starts and ends,
your meal times, when you need a break, and after which appointments Iris asks how it went. Your home
address and your calendars are set in the plugins that own them (travel or maps, calendars, google).

## For the curious

```
planner                                    today
planner day <day>                          another day
planner next                               now and next
planner sources                            which plugins it reads
planner leave [<appointment>] [--soon]     when to leave
planner near <appointment|address>         parking and food
planner person <name> [kid|partner|family|team]      planner people
planner owner <calendar|word> <who> [--bring <who>] [--pick <who>]
planner owners                             planner owner remove <calendar|word>
planner prep <appointment> ["<task>"]
planner review <appointment> [--feeling <word>] [--outcome "<text>"] [--action "<text>"]...
planner reviews                            planner evaluate on|off <word>
planner task "<title>" [<day>] [--before <appointment>]
planner promise "<title>" [<day>]
planner done|undo|drop <#id>               planner tasks [<day>|later]
planner move <#id>[,<#id>] <tomorrow|overmorrow|nextweek|later|<day>>
planner recap                              planner tomorrow
```

Promises, tasks, reviews and who is who live in the plugin's own database, in your house.

## Permissions

None of its own. It runs the commands of the plugins above, which keep their own permissions and keys;
the planner never reaches the internet or the vault itself.
