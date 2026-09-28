# Hours

Keep the hours you work, by talking to Iris or on the Hours screen. Start a timer when you begin, stop it
when you are done, or say afterwards what you did: "two and a half hours on the Bakker website yesterday".
Everything is kept in the plugin's own database in your house. No account and no key.

## What it does

- **A timer**: start it on a project, stop it later (or say when you stopped, when you forgot). Starting
  another project stops the first. It can round up to 5, 6, 10, 15 or 30 minutes.
- **Hours afterwards**: `2,5`, `1:30`, `90m` or a span like `09:00-12:30`, on any day that has been.
- **Projects and clients**, each with an hourly rate; internal projects are not billable.
- **Your week and month**: per day, per project, against the hours of your working week, and what they are
  worth.
- **Invoicing**: what is still to invoice per project, with the amount before VAT, and marking it as
  invoiced once the invoice is out, so it is never counted twice.
- **CSV export** per week, month or project, with commas or with semicolons and decimal commas for a Dutch
  Excel.

## The screen

The Hours screen shows the running timer counting on, start buttons for your recent projects, today and
this week, a form to add hours, the week per day and per project, and every entry with a way to remove
it. Earlier weeks are one button away.

## Talking to Iris

- `hours` - the timer, today and this week
- `hours start "Website Bakker"`, `hours stop`, `hours stop at 17:30`
- `hours add 2,5 "Website Bakker" yesterday "meeting"`
- `hours week`, `hours week last`, `hours month`, `hours month 2026-09`
- `hours list week`, `hours edit <id> hours 1:45`, `hours remove <id>`
- `hours project add "Website Bakker" client "Bakker BV" rate 85`, `hours projects`
- `hours invoice Bakker 2026-09`, then `hours invoice Bakker 2026-09 done`
- `hours export last month`

## Settings

| Setting | What it does |
|---|---|
| Currency | For rates and amounts. EUR by default. |
| Hours in a working week | What the week is measured against. 40 by default, 0 for none. |
| Round the timer up to | 0 keeps the exact minutes. |
| CSV for | Comma, or semicolon with decimal commas. |

Exports are written to `exports/` in the plugin's folder.
