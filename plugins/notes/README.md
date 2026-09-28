# Notes

Quick notes you say out loud and find again later. Kept in the plugin's own database inside your house:
no account, no internet, nothing leaves it.

## What it does

- `notes` - the latest notes, pinned ones first
- `notes add <text>` - keep a note; words like `#work` become its tags
- `notes find <text>` or `notes find #tag`
- `notes show <id>`, `notes edit <id> <text>`, `notes append <id> <text>`
- `notes pin <id>`, `notes unpin <id>`, `notes remove <id>`
- `notes tags` - every tag and how many notes carry it

## Say to Iris

- "Note that the plumber comes on Tuesday."
- "What did I write down about the plumber?"
- "Show my gift ideas." (with notes tagged `#gift`)

## Permissions

None. The notes live in `data.db` in the plugin's own folder.
