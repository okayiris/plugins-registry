# Process Monitor

See what runs inside your house. A live screen (and a command) that lists every process with the user,
cpu, memory and age, plus the workbench boxes that are busy right now. Built for an owner who wants to know
what is going on, and to be able to stop one thing that got stuck.

- **Read-only by default.** Everything is gathered from `/proc`; just looking never changes anything.
- **Stopping asks first.** The command refuses without `--ja` and prints how to confirm. On the screen a
  second, deliberate tap is needed. Nothing is ever stopped silently.
- **The floor is protected.** Pid 1, the desktop, the assistant itself, the bridge and the command's own
  process tree are shown with the reason instead of a stop button, and the command refuses to stop them.
- **Workbench boxes.** While a workbench job runs, its wrapper process is visible here with the folder, the
  command and its age. The workbench service itself has no list route, so a box is only shown while it runs;
  that is exactly what "is it still busy?" asks.
- No keys, no data of the owner, nothing is sent anywhere.

## Usage

```
processes                 a short summary: how many processes, the heaviest, the boxes
processes procs [--all]   the process table (--all also shows the floor and zombies)
processes boxes           the workbench boxes that are busy right now
processes stop <pid>      ask to stop one process (TERM)
processes stop <pid> --hard --ja   stop it for real (KILL)
```

`--json` prints the same as one object. `procs` also answers to `processen`; `boxes` to `boxen` and
`werkplekken`; `--all` to `--alles`. The confirmation flag stays `--ja`.

## Permissions

- **files**: reads `/proc` outside its own folder. Stopping a process needs no key; it only works on
  processes the house itself owns.

## Screen

`plugin open process-monitor` shows the live screen: totals, memory, the busy boxes and the process list,
refreshing every few seconds. Stop buttons never touch a protected process.
