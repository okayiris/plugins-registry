# Family agenda

The family agenda in a few lines, read from the Google agenda of this house. Iris shows what is
coming up and can put something new in the agenda after the owner approves it on screen.

## Commands

```
family-agenda                                  today and tomorrow
family-agenda week                             the next seven days
family-agenda zoek <tekst>                     search on title or place
family-agenda plan "<titel>" <datum> <tijd>    put something in the agenda
        [--wie naam] [--waar plaats] [--proef]
family-agenda lid <naam> [e-mail]              remember a family member
family-agenda lid                              show the family members
family-agenda lid weg <naam>                   forget a family member
```

- Dates are `YYYY-MM-DD`, times are `HH:MM`. A plan lasts one hour by default.
- `--wie naam` adds a guest. When the name has a known e-mail (see `family-agenda lid`), Google
  sends the invitation; otherwise the name goes into the note.
- `--proef` shows the exact `google cal add` command without running it.
- Planning goes through `google cal add`, which puts an **Approve** button on the owner's screen.
  Nothing is placed without that tap.

## Window

`family-agenda.jsx` is the plugin's window: a small form with a **date picker** (`input type="date"`),
a **time picker** (`input type="time"`), a field for what it is and optional fields for who and where.
The button sends `nova("family-agenda plan ...")`, so the plan runs exactly as if the owner had typed
it, and the usual approval still appears.

## Google

The agenda comes from the `google` command of this house (`google cal list`), the same connection used
on the Integrations screen. Iris only reads; the plugin never changes the agenda on its own. When
Google is not linked, the command says so in one line and stops.

## Family members

Family members are kept in `settings.json` in the plugin folder. That is not secret and holds only
names and optional e-mail addresses, so `--wie mama` can become a real invitation when an address is
known.

## Permissions

- `internet`: needed for the agenda through the house's Google connection. The plugin itself holds no
  key.
