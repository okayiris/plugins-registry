---
name: tensions
description: Holacracy tensions through the tensions plugin, in its own database. A tension is the sensed gap between how things are and how they could be, always from one of the owner's roles; neutral, from irritation to enthusiasm. Note them, triage them for the tactical or governance meeting, build a meeting agenda, and record how each was processed.
whenToUse: When the owner names something that could be better in their work or organisation (missing information, unclear responsibility, a chance being missed), uses the words tension or spanning, prepares a tactical or governance meeting, or says a tension was resolved. Not for plain to-dos without a sensed gap (todoist) or personal notes (notes).
---

# tensions

```sh
tensions                                                   # open, per role
tensions add Marketing Lead: I miss information about project X --tactical
tensions add Facilitator: unclear who owns the invoices --governance --weight 3
tensions add Sales: a market we now miss --opportunity --circle "Sales"
tensions agenda tactical                                   # for the next tactical meeting
tensions triage 4 governance
tensions process 2 next-action: Jan sends the figures every Monday
tensions process 5 role: new role Invoicing, accountable for sending invoices
tensions settings set roles Marketing Lead, Facilitator
```

- Always from a role. Unsure which? Ask once, naming the roles from `tensions settings`.
- Write the tension down neutrally, as the gap the owner senses, in their words; not as blame on a person.
- Triage: operational work, a next action, a project, information or help is `--tactical`; roles,
  accountabilities, domains and policies are `--governance`. Leave it out when it is not clear yet.
- `--weight 3` when it clearly pulls hard, `1` for a small itch; `--opportunity` for a chance rather than a gap;
  `--since 2026-09-21` when the owner has felt it for a while already.
- Outcomes: next-action, project, information, help, role, policy, election, dropped.
- The widget shows the overview; `plugin open tensions` shows the board. Ask before `tensions delete`.
