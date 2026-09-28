# Todoist

Your [Todoist](https://todoist.com) tasks by voice: what is due today and this week, adding a task with
a date in plain words, and ticking one off.

## What it does

- `todoist` - today and overdue, numbered
- `todoist week` - the next seven days
- `todoist add "<task>" [when]` - like `todoist add "Call the plumber" tomorrow 9am`
- `todoist done <number or text>`
- `todoist projects`, `todoist project <name>`, `todoist search <text>`

It adds and closes tasks when you ask; it never deletes anything.

## Setup

1. In Todoist, open Settings, Integrations, Developer, and copy your API token.
2. Say "connect Todoist" (or run `todoist key ask`): a safe window opens to paste it into the vault.

## How the token is used

The plugin never reads it. Every call is made by the vault with the token filled in as `{g}` in the
`Authorization` header; only Todoist's answer comes back.

## Say to Iris

- "What do I have to do today?"
- "Put 'call the plumber' on my list for tomorrow at nine."
- "The groceries are done."

## Permissions

`internet` and `secrets`: to reach the Todoist API with your token from the vault.
