# Workers

See live which workers are running for this house and what they are doing. The plugin adds a page of its
own at `/workers`: it polls the house for running work every two seconds and draws each one as a row with a
coloured dot, the title, the first line of what it is doing, the status word and how long it has been
running. Running workers come first, and the time ticks in minutes and seconds. When nothing is running it
shows one dim line. If the house does not answer it keeps the last list and shows a small "no answer".

It is a read-only view. Nothing is clickable and no data leaves the house.

## The page

Open `/workers` on this house's address. The page sits behind the house sign-in. It shows:

- a heading with how many workers are live,
- one row per running worker with a coloured dot for working, waiting, done or stuck,
- the title and the first line of what the worker is doing,
- the status word and the elapsed time in minutes and seconds,
- a dim line that Talvi keeps an eye on them.

## The command

```
workers    one line per running worker, for example "Focus plugin - working 2m 14s"
```

It reads the same live list, prints nothing when no worker is running, and never crashes.

## What it costs

Nothing. No account, no key and no internet.
