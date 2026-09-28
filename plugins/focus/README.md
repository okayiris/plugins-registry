# Focus

A small focus timer. Start a block of 25 minutes, pause when something interrupts you, resume, and see how
many minutes you focused today. The window shows a live countdown with a ring, and the command keeps the
daily total.

## What you can ask

- "Start a focus block."
- "Start a focus block of 50 minutes."
- "Pause my focus."
- "Resume my focus."
- "Stop my focus."
- "How long is left?"
- "How much did I focus today?"

## The command

```
focus                  minutes left and end time, or that nothing is running, plus today's total
focus status           the same
focus start [minutes]  start a block, 25 minutes by default
focus pause            pause the running block
focus resume           resume a paused block
focus stop             stop and add the focused minutes to today
focus today            today's total focused time
```

A block runs in the background. Only the minutes you actually focused are added to today, so time spent
paused does not count. The state stays in `state.json` in the plugin's own folder, and no data leaves your
house.

## The window

The window is a countdown from 25 minutes with a ring, a Start button, Pause and Resume, and Reset. It
fills any size you give it.

## What it costs

Nothing. No account and no key.
