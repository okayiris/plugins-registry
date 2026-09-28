# GitHub

Read public repositories, files, issues and pull requests on GitHub without a key, and write
branches, commits and pull requests with a token that stays in the vault. It also registers
webhooks for a repository and can call any GitHub endpoint by hand.

## What it does

Reading public work needs nothing:

```sh
gh repo cli/cli
gh file cli/cli README.md
gh tree cli/cli
gh issues cli/cli --limit 5
gh issue cli/cli 14529 --comments
gh prs cli/cli
gh pr cli/cli 14519 --files
gh commits cli/cli
gh branches cli/cli
gh releases cli/cli
gh search "language:python stars:>1000" --type repos
gh user cli
```

Set the repository you use most once, then leave it out:

```sh
gh default cli/cli
gh prs
```

Writing uses a GitHub token from the vault:

```sh
gh branch cli/cli my-branch --from trunk
gh commit cli/cli my-branch "Add a note" README.md="New line" notes/todo.txt=@todo.txt
gh pr create cli/cli --head my-branch --base trunk --title "Add a note" --body "What and why"
gh pr comment cli/cli 42 "Looks good to me"
gh issue create cli/cli --title "A bug" --body "Steps" --labels bug
gh issue comment cli/cli 42 "Thanks, reproduced"
```

`gh commit` reads a local file with `@path`, otherwise the text after `=` is the content. Text and
binary files both work.

## The token

The plugin never sees the token. Ask once and paste a fine-grained token in the vault window:

```sh
gh token ask
```

Use a token limited to the repositories you name, with **Contents**, **Issues** and **Pull
requests** write access. For `gh hook add` it also needs **Administration** write. The call itself
is made by the vault, with the token filled in as `{g}`; only the answer comes back. Check with
`gh token`, and point it at another vault item with:

```sh
gh token item my-github --domain api.github.com
```

## Webhooks

The house receives an event on the incoming webhook you make on the Integrations screen. Save that
address, register it on GitHub, and test the action:

```sh
gh hook url
gh hook url "https://.../webhook/..."     # the address from the Integrations screen
gh hook add cli/cli --events push,issues,pull_request
gh hooks cli/cli
gh hook rm cli/cli 123456789
gh hook test --event pull_request --repo cli/cli
```

`gh hook test` sends a sample `push`, `issues` or `pull_request` event to the house's route, so you
can see the action arrive without waiting for a real change. `gh hook send` takes your own JSON.
A webhook address is kept in `.state.json` next to this plugin (mode 600) and is never printed whole.

## Any endpoint

```sh
gh api /repos/cli/cli
gh api /repos/cli/cli/issues --method POST --body '{"title":"A bug"}'
gh api /user --token
gh api /repos/octocat/Hello-World --header "Accept: application/vnd.github+json"
```

Without `--token` the call is made directly, so extra headers work. With `--token` the vault sends
the token header; use it for anything that must be authenticated. GitHub's defaults cover
`Accept` and the API version, so a separate header is rarely needed.

## Permissions

- **internet** - everything it reads and writes goes to `api.github.com`.
- **secrets** - it uses a vault item, but never reads the value.

## Notes

- Public reading is rate limited to 60 requests an hour per address; a token raises that.
- Nothing of yours is stored except the default repository and the webhook address in `.state.json`.
- No key, name or repository of one owner is baked into the code.
