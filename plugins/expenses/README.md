# Expenses

Keep what you spend by saying it. Iris adds it up per month and per category, compares a month with
the one before, and keeps an eye on the budgets you set. Everything stays in the plugin's own database
inside your house.

## What it does

- `expenses` - this month: the total, per category, and against your budgets
- `expenses add <amount> <category> [note] [yesterday|YYYY-MM-DD]`
- `expenses list [YYYY-MM]` - every expense of a month
- `expenses month [YYYY-MM]` - per category, against the month before
- `expenses budget <category> <amount>` - a monthly budget
- `expenses remove <id>`, `expenses categories`

## Say to Iris

- "I spent 42 euro on groceries."
- "How much did I spend on eating out this month?"
- "Set my groceries budget to 400 euro."

## Permissions

None. The expenses live in `data.db` in the plugin's own folder.
