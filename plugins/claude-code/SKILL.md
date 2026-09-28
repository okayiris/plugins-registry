---
name: claude-code
description: Claude Code, Anthropic's coding agent, running inside the house on the owner's own project folders. Read-only questions about code, coding tasks that edit files (and run commands only when allowed), background runs, and going on in the same conversation.
whenToUse: When the owner wants something done in code or a project in the house (build, fix, refactor, write tests, explain code), or asks Claude Code by name. Not for code on their own computer (node) or for GitHub itself (github).
---

# claude-code

```sh
claude-code                                         # installed? signed in? the last run
claude-code folders                                 # the projects under ~/code
claude-code ask "what does this project do?" --in site
claude-code do "fix the failing test" --in shop
claude-code do "run the tests and fix what fails" --in shop --shell
claude-code start "write a README" --in photos      # background; returns at once
claude-code runs                                    # busy or done
claude-code result 4                                # the whole answer of run 4
claude-code more "also add a test for it"           # same conversation, same folder, last run
claude-code stop 4
```

- A question is `ask` (it only reads). A change is `do`. Anything that will take more than a few minutes is
  `start`, then tell the owner you will look when they ask, and use `runs` and `result` then.
- Add `--shell` only when the owner allows commands (running tests, installing packages, git). If a run says
  it was not allowed to use Bash, ask the owner before going on with `more "go on" <run> --shell`.
- Say what it changed in a sentence or two; the whole answer is in `result`.
- Not installed: `claude-code install`. Not signed in: the owner types `claude-code login` in the house's
  terminal once (a Claude plan, or `login console` for an Anthropic Console account). Never ask for a key in chat.
