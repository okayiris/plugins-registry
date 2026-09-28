# Claude Code

[Claude Code](https://code.claude.com), Anthropic's coding agent, in your own house. It runs in the house's
private workspace, on the projects that live there: ask Iris a question about your code, or give her a task,
and Claude Code reads, edits and (only when you allow it) runs commands in that one project folder.

- **Ask** about a project: it only reads. "What does the backup script do, and where does it go wrong?"
- **Do** a task: it may edit files in that folder. "Add a dark mode to my site."
- **Start** a longer task in the background, and ask later how it went.
- **More**: go on in the same conversation, with the same folder.

## What you need

- A Claude plan (Pro or Max) or an Anthropic Console account. Runs are paid there; installing is free.
- Claude Code in the house: say "install Claude Code" (`claude-code install`, from npm, into the plugin's
  own folder). A `claude` that is already on the house's path is used first.
- Sign in once, in the house's terminal: `claude-code login` (or `claude-code login console`). The login is
  kept by Claude Code itself in the plugin's folder (`.claude/`); the plugin's own code never reads it, and it
  is never published.

## Try saying

- "Ask Claude Code what my weather-station project does."
- "Let Claude Code fix the failing test in the shop project, and it may run commands."
- "Start Claude Code on a README for the photos project, and tell me when I ask."
- "How did the last Claude Code run go?"

## Commands

```sh
claude-code                                   installed, signed in, the folder, the last run
claude-code ask "<question>" --in <folder>    read-only
claude-code do "<task>" --in <folder>         may edit files there
claude-code do "<task>" --in <folder> --shell and run commands there
claude-code start "<task>" --in <folder>      the same, in the background (--read-only to only read)
claude-code more "<text>" [<run>]             go on in the same conversation
claude-code runs | result [<run>] | stop <run>
claude-code folders
claude-code install | update | login | logout
```

A folder is a name under the projects folder (`~/code` by default; a task makes it when it is new) or a whole
path. It is never the whole house or the plugin's own folder.

## Safety

- Every tool Claude Code is not given is refused, never asked: read-only runs get Read, Grep and Glob; tasks add
  Edit and Write; only `--shell` (or the setting) adds Bash.
- Each run has a budget (2 dollars by default) and a time limit in the foreground (20 minutes).
- `claude-code stop <run>` stops a background run; what it already changed stays.

## Settings

Projects folder, model, whether tasks may run commands, the budget per run and the minutes in the foreground.

## Permissions

- **internet**: Claude Code talks to Anthropic, and `install` fetches it from npm.
- **files**: it reads and edits your project folders, outside the plugin's own folder.
