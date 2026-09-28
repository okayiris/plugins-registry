---
name: expenses
description: The owner's own spending, said out loud and kept in the expenses plugin's database. This month per category, a month compared with the one before, every expense of a month, and monthly budgets per category.
whenToUse: When the owner says they paid or spent something, asks how much they spent (this month, on something), whether they are within budget, or wants a budget set. Not for bank statements or invoices (moneybird, stripe).
---

# expenses

```sh
expenses                                  # this month, per category, against budgets
expenses add 42,50 groceries              # today
expenses add 18 dinner pizza yesterday    # a note after the category, a day at the end
expenses list 2026-08
expenses month                            # this month against the one before
expenses remove 12
expenses budget groceries 400
expenses budget                           # all budgets
expenses categories
```

- Use one short lowercase word per category and reuse the ones already there (`expenses categories`):
  "I bought bread" goes in groceries when groceries exists.
- After adding, answer in one sentence with what is left of the budget when there is one.
- Ask before `expenses remove`.
