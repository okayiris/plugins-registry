# Tensions

In Holacracy a **tension** is the gap you sense between how things are now and how they could be. It is
not a complaint and not personal: a neutral signal, from a light irritation to real enthusiasm, that
something could be better. You always sense it from one of your roles, and it is the fuel that keeps
roles, processes and agreements improving.

This plugin keeps your tensions in view: note one by saying so, triage it for the tactical or the
governance meeting, and see at a glance what is open, per role, which ones weigh most and which have
been waiting too long. Kept in the plugin's own database in your house.

## What it does

- **Widget**: the number of open tensions, tactical, governance, not yet triaged and waiting long, with
  the heaviest few and the role they come from.
- **Board** (a whole screen): every open tension grouped per role, filters for tactical, governance, not
  triaged and opportunities, a tap to triage, and a tap to process one with its outcome: a next action, a
  project, information, help, a role change, a policy, an election, or dropped.
- `tensions` - what is open, per role
- `tensions add <role>: <text>` with `--circle`, `--tactical` or `--governance`, `--weight 1-3`, `--opportunity`, `--since <date>`
- `tensions agenda [tactical|governance]` - the agenda for the next meeting, heaviest first
- `tensions triage <id> tactical|governance`, `tensions weight <id> 1-3`
- `tensions process <id> <outcome>[: <note>]`, `tensions reopen <id>`
- `tensions list`, `tensions show <id>`, `tensions roles`, `tensions edit`, `tensions delete`

## Settings

- **Your roles**: the roles you fill. With one role, a tension without a role goes there.
- **Your circle**: where a new tension belongs when you name none.
- **Waiting too long after**: days before an open tension is marked (14).

## Say to Iris

- "As Marketing Lead I miss information about project X to do my work well."
- "It is unclear who is responsible for the invoices; that is a governance tension."
- "I see an opportunity in the market we are missing now."
- "What is on the agenda of the tactical meeting?"
- "Tension 3 is done: Jan sends the figures every Monday."

## Permissions

None. The tensions live in `data.db` in the plugin's own folder.
