#!/usr/bin/env python3
"""GitHub for Iris: read public repositories, files, issues and pull requests without a key,
and write branches, commits and pull requests with a token from the vault.

  gh repo [<owner/name>]                 what the repository is
  gh default [<owner/name>]              show or set the repository later commands use
  gh file <owner/name> <path> [--ref R]  one file, or what is in a folder
  gh tree <owner/name> [<path>] [--ref R]
                                         a folder, deeper, up to a limit
  gh issues <owner/name> [--state open|closed|all] [--limit n] [--label L]
  gh issue <owner/name> <number> [--comments]
  gh prs <owner/name> [--state open|closed|all] [--limit n]
  gh pr <owner/name> <number> [--files]
  gh commits <owner/name> [--ref R] [--limit n]
  gh branches <owner/name>
  gh releases <owner/name> [--limit n]
  gh search "<query>" [--type repos|issues|prs|code] [--limit n]
  gh user <login>

  gh token                               is there a token, and which vault item
  gh token ask                           let the owner paste one in the vault
  gh token item <name> [--domain D]      use another vault item
  gh branch <owner/name> <branch> [--from main]
  gh commit <owner/name> <branch> "<message>" <path>=<text|@file> ...
                                         one commit on that branch (made from --from if new)
  gh pr create <owner/name> --head <branch> --base <base> --title "..." [--body "..."] [--draft]
  gh pr comment <owner/name> <number> "<text>"
  gh issue create <owner/name> --title "..." [--body "..."] [--labels a,b]
  gh issue comment <owner/name> <number> "<text>"

  gh hooks <owner/name>                  the webhooks GitHub has for the repository
  gh hook url [<url>]                    show or save the house's incoming webhook address
  gh hook add <owner/name> [--url U] [--events push,issues,pull_request]
  gh hook rm <owner/name> <id>
  gh hook test [--event push|issues|pull_request] [--repo owner/name]
  gh hook send <event> [--data "<json>"] [--url U]
                                         send an event to the house's webhook route

  gh api <path-or-url> [--method GET|POST|PATCH|PUT|DELETE] [--body "<json|@file>"]
         [--header "Accept: application/vnd.github+json"] ... [--token]
                                         any GitHub endpoint, with the token when asked

Reading a public repository needs no key: `gh repo cli/cli`, `gh issues cli/cli` and
`gh prs cli/cli` work as they are. Writing (branch, commit, pull request, issue, webhook) and
`gh api --token` use a GitHub token from the vault; this tool never sees the value. Ask for one
once with `gh token ask` and paste a fine-grained token with Contents, Issues and Pull requests
write, and Administration write if you want `gh hook add`. Nothing is stored in this folder
except the repository and webhook address you set yourself.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(HERE, ".state.json")
API = "https://api.github.com"
UA = "Iris-github/1.0"
DEFAULT_ITEM = "github-api"
DEFAULT_DOMAIN = "api.github.com"
DEFAULT_EVENTS = ["push", "issues", "pull_request"]
FILE_CHARS = 6000


def fail(text):
    print("github: " + text)
    sys.exit(1)


# ---------------------------------------------------------------- state

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE)


def default_repo():
    return (load_state().get("repo") or "").strip()


def hook_url():
    return (load_state().get("hook_url") or "").strip()


def token_item():
    return (load_state().get("token_item") or DEFAULT_ITEM).strip()


def token_domain():
    return (load_state().get("token_domain") or DEFAULT_DOMAIN).strip()


# ---------------------------------------------------------------- the vault

def vault_bin():
    p = shutil.which("kluis") or shutil.which("vault")
    if p:
        return p
    p = os.path.expanduser("~/.local/bin/kluis")
    return p if os.path.isfile(p) else None


def vault_items():
    exe = vault_bin()
    if not exe:
        return []
    try:
        proc = subprocess.run([exe, "lijst"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    out = (proc.stdout or "").strip()
    if not out or "leeg" in out.lower() or "empty" in out.lower():
        return []
    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("de kluis"):
            continue
        names.append(re.split(r"\s{2,}", line)[0].strip())
    return names


def have_token():
    return token_item() in vault_items()


def require_token():
    if not have_token():
        fail(f'no GitHub token in the vault yet (I looked for "{token_item()}"). '
             "Run `gh token ask` first; the vault asks you to paste it, this tool never sees it.")


def vault_call(item, method, url, body=None):
    """Let the vault make the call, so the token never enters this process. Returns (status, text)."""
    exe = vault_bin()
    if not exe:
        fail("the vault command (kluis) is not on this system")
    cmd = [exe, "doe", item, method, url]
    if body is not None:
        cmd.append(body)
    cmd += ["--kop", "Authorization: Bearer {g}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        fail("GitHub did not answer in time")
    out = (proc.stdout or "").strip()
    first, _, rest = out.partition("\n")
    if first.startswith("status "):
        try:
            return int(first.split()[1]), rest.strip()
        except (IndexError, ValueError):
            pass
    msg = (proc.stderr or out).strip() or "the vault refused the call"
    for pre in ("kluis:", "vault:"):
        if msg.startswith(pre):
            msg = msg[len(pre):].strip()
    fail(msg)


# ---------------------------------------------------------------- http

def direct(method, url, headers, data):
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except OSError as e:
        fail(f"cannot reach the address ({e})")


def request(method, path, body=None, token=False, headers=None):
    url = path if path.startswith("http://") or path.startswith("https://") else API + path
    hdrs = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if headers:
        hdrs.update(headers)
    text = None
    if body is not None:
        text = body if isinstance(body, str) else json.dumps(body)
        hdrs.setdefault("Content-Type", "application/json")
    if token:
        require_token()
        if headers:
            print("note: the vault sends the token header; other --header values work without --token",
                  file=sys.stderr)
        return vault_call(token_item(), method, url, text)
    return direct(method, url, hdrs, text.encode("utf-8") if text is not None else None)


def github_error(status, text):
    message = ""
    try:
        message = (json.loads(text) or {}).get("message", "")
    except (ValueError, AttributeError):
        message = text[:200]
    if status == 401:
        return "GitHub refused the token (401). Put a fresh one in the vault with `gh token ask`."
    if status == 404:
        return "not found on GitHub (404). Check the repository, branch or number."
    if status in (403, 429) and "rate limit" in message.lower():
        return "GitHub's rate limit is reached. Wait a bit, or use a token with `--token`."
    if status == 422:
        return f"GitHub rejected it (422): {message or 'the values are not right'}"
    return f"GitHub returned {status}: {message or 'unknown error'}"


def api_json(method, path, body=None, token=False, headers=None):
    status, text = request(method, path, body=body, token=token, headers=headers)
    if status >= 400:
        fail(github_error(status, text))
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        fail("GitHub did not return JSON")


# ---------------------------------------------------------------- small helpers

def parse(args, valued=(), flags=(), repeated=()):
    pos = []
    opts = {}
    i = 0
    while i < len(args):
        x = args[i]
        if x.startswith("--"):
            k = x[2:]
            if k in valued or k in repeated:
                if i + 1 >= len(args):
                    fail(f"--{k} needs a value")
                v = args[i + 1]
                i += 2
                if k in repeated:
                    opts.setdefault(k, []).append(v)
                else:
                    opts[k] = v
            elif k in flags:
                opts[k] = True
                i += 1
            else:
                fail(f"unknown option --{k}")
        else:
            pos.append(x)
            i += 1
    for k in repeated:
        opts.setdefault(k, [])
    return pos, opts


def repo_of(pos, i=0):
    if len(pos) > i and pos[i]:
        return pos[i]
    repo = default_repo()
    if repo:
        return repo
    fail("which repository? Give owner/name, like `gh repo cli/cli`.")


def number(value, what="number"):
    try:
        return int(value)
    except (TypeError, ValueError):
        fail(f"{what} must be a number, got {value!r}")


def limit_of(opts, default=10, most=50):
    n = number(opts.get("limit", default), "--limit")
    return max(1, min(n, most))


def when(iso):
    return (iso or "")[:10]


def mask_url(url):
    """Never show a webhook address whole: the path is its secret."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return "(address)"
    path = u.path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    shown = "/" + "/".join(parts[:1] + ["..."]) if len(parts) > 1 else path
    return f"{u.scheme}://{u.netloc}{shown}"


def read_value(value):
    """A file value is text, or @path to read a local file (utf-8, else base64)."""
    if value.startswith("@"):
        path = os.path.expanduser(value[1:])
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            fail(f"cannot read {path} ({e})")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw
    return value


# ---------------------------------------------------------------- reading

def cmd_repo(pos, opts):
    repo = repo_of(pos)
    d = api_json("GET", f"/repos/{repo}")
    print(d.get("full_name", repo))
    if d.get("description"):
        print(d["description"])
    bits = [f"{d.get('stargazers_count', 0)} stars", f"{d.get('forks_count', 0)} forks",
            f"{d.get('open_issues_count', 0)} open issues"]
    print(", ".join(bits))
    line = [f"default branch {d.get('default_branch', '?')}"]
    if d.get("language"):
        line.append(d["language"])
    if (d.get("license") or {}).get("spdx_id"):
        line.append(d["license"]["spdx_id"])
    print(", ".join(line))
    print(f"{d.get('html_url', '')} (updated {when(d.get('updated_at'))})")


def cmd_default(pos, opts):
    if not pos:
        repo = default_repo()
        print(f"default repository: {repo}" if repo else "no default repository yet, set one with `gh default owner/name`")
        return
    repo = pos[0]
    if "/" not in repo:
        fail("give owner/name, like `gh default cli/cli`")
    s = load_state()
    s["repo"] = repo
    save_state(s)
    print(f"default repository: {repo}")


def cmd_file(pos, opts):
    repo = repo_of(pos, 0)
    if len(pos) < 2:
        fail("gh file <owner/name> <path>")
    path = pos[1].lstrip("/")
    ref = opts.get("ref")
    url = f"/repos/{repo}/contents/{urllib.parse.quote(path, safe='/')}"
    if ref:
        url += "?ref=" + urllib.parse.quote(ref, safe="")
    d = api_json("GET", url)
    if isinstance(d, list):
        print(f"{path or '/'} in {repo}:")
        for x in sorted(d, key=lambda y: (y.get("type") != "dir", y.get("name", "")))[:100]:
            kind = "dir " if x.get("type") == "dir" else "file"
            print(f"  {kind} {x.get('name')}")
        return
    name = d.get("name", path)
    size = d.get("size", 0)
    if d.get("encoding") == "base64" and d.get("content"):
        raw = base64.b64decode(d["content"])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            print(f"{name}: a binary file of {size} bytes.")
            if d.get("download_url"):
                print(d["download_url"])
            return
        print(f"{name} ({size} bytes)")
        print("")
        if len(text) > FILE_CHARS:
            print(text[:FILE_CHARS])
            print(f"... cut off after {FILE_CHARS} of {len(text)} characters")
        else:
            print(text.rstrip())
    else:
        print(f"{name}: {size} bytes, not shown.")
        if d.get("download_url"):
            print(d["download_url"])


def cmd_tree(pos, opts):
    repo = repo_of(pos, 0)
    path = (pos[1] if len(pos) > 1 else "").strip("/")
    ref = opts.get("ref") or ""
    d = api_json("GET", f"/repos/{repo}/contents/{urllib.parse.quote(path, safe='/')}" + (f"?ref={urllib.parse.quote(ref)}" if ref else ""))
    if not isinstance(d, list):
        fail(f"{path or '/'} is a file, not a folder; use `gh file`")
    for x in sorted(d, key=lambda y: (y.get("type") != "dir", y.get("name", ""))):
        kind = "dir " if x.get("type") == "dir" else "file"
        print(f"{kind} {x.get('name')}")
    print(f"({len(d)} entries in {repo}/{path})")


def cmd_issues(pos, opts):
    repo = repo_of(pos)
    state = opts.get("state", "open")
    n = limit_of(opts)
    url = f"/repos/{repo}/issues?state={urllib.parse.quote(state)}&per_page={n}&sort=updated&direction=desc"
    if opts.get("label"):
        url += "&labels=" + urllib.parse.quote(opts["label"])
    d = api_json("GET", url)
    items = [x for x in (d or []) if "pull_request" not in x]
    if not items:
        print(f"no {state} issues in {repo}")
        return
    for x in items:
        who = (x.get("user") or {}).get("login", "?")
        labels = ", ".join(l.get("name", "") for l in x.get("labels", []))
        line = f"#{x.get('number')} {x.get('title')} ({x.get('state')}) by {who}"
        if labels:
            line += f" [{labels}]"
        line += f", {x.get('comments', 0)} comments, {when(x.get('updated_at'))}"
        print(line)


def cmd_issue(pos, opts):
    repo = repo_of(pos, 0)
    if len(pos) < 2:
        fail("gh issue <owner/name> <number>")
    num = number(pos[1])
    d = api_json("GET", f"/repos/{repo}/issues/{num}")
    if "pull_request" in d:
        fail(f"#{num} is a pull request; use `gh pr {repo} {num}`")
    print(f"#{d.get('number')} {d.get('title')}")
    who = (d.get("user") or {}).get("login", "?")
    labels = ", ".join(l.get("name", "") for l in d.get("labels", []))
    print(f"{d.get('state')} by {who}" + (f" [{labels}]" if labels else ""))
    print(d.get("html_url", ""))
    if d.get("body"):
        print("")
        body = d["body"].strip()
        print(body[:FILE_CHARS] + ("\n... cut off" if len(body) > FILE_CHARS else ""))
    if opts.get("comments"):
        c = api_json("GET", f"/repos/{repo}/issues/{num}/comments?per_page=20") or []
        for x in c:
            print("")
            print(f"{(x.get('user') or {}).get('login', '?')} on {when(x.get('created_at'))}:")
            print((x.get("body") or "").strip()[:1000])


def cmd_prs(pos, opts):
    repo = repo_of(pos)
    state = opts.get("state", "open")
    n = limit_of(opts)
    d = api_json("GET", f"/repos/{repo}/pulls?state={urllib.parse.quote(state)}&per_page={n}&sort=updated&direction=desc")
    if not d:
        print(f"no {state} pull requests in {repo}")
        return
    for x in d:
        who = (x.get("user") or {}).get("login", "?")
        head = (x.get("head") or {}).get("ref", "?")
        base = (x.get("base") or {}).get("ref", "?")
        draft = " draft" if x.get("draft") else ""
        print(f"#{x.get('number')} {x.get('title')} ({x.get('state')}{draft}) {head} -> {base} by {who}, {when(x.get('updated_at'))}")


def cmd_commits(pos, opts):
    repo = repo_of(pos)
    n = limit_of(opts)
    url = f"/repos/{repo}/commits?per_page={n}"
    if opts.get("ref"):
        url += "&sha=" + urllib.parse.quote(opts["ref"])
    d = api_json("GET", url)
    for x in d or []:
        sha = (x.get("sha") or "")[:7]
        c = x.get("commit") or {}
        msg = (c.get("message") or "").splitlines()[0]
        who = ((c.get("author") or {}).get("name")) or "?"
        print(f"{sha} {msg} by {who}, {when((c.get('author') or {}).get('date'))}")


def cmd_branches(pos, opts):
    repo = repo_of(pos)
    d = api_json("GET", f"/repos/{repo}/branches?per_page=50")
    for x in d or []:
        sha = ((x.get("commit") or {}).get("sha") or "")[:7]
        print(f"{x.get('name')} {sha}")


def cmd_releases(pos, opts):
    repo = repo_of(pos)
    n = limit_of(opts)
    d = api_json("GET", f"/repos/{repo}/releases?per_page={n}")
    if not d:
        print(f"no releases in {repo}")
        return
    for x in d:
        print(f"{x.get('tag_name')} {x.get('name') or ''} ({when(x.get('published_at'))})")


def cmd_search(pos, opts):
    if not pos:
        fail('gh search "<query>" [--type repos|issues|prs|code]')
    query = " ".join(pos)
    kind = opts.get("type", "repos")
    endpoint = {"repos": "repositories", "issues": "issues", "prs": "issues", "code": "code"}.get(kind)
    if not endpoint:
        fail("--type must be repos, issues, prs or code")
    if kind == "prs" and "is:pr" not in query:
        query += " is:pr"
    if kind == "issues" and "is:issue" not in query:
        query += " is:issue"
    n = limit_of(opts)
    d = api_json("GET", f"/search/{endpoint}?q={urllib.parse.quote(query)}&per_page={n}",
                 token=(kind == "code"))
    print(f"{d.get('total_count', 0)} results")
    for x in (d.get("items") or [])[:n]:
        if kind == "repos":
            print(f"{x.get('full_name')} {x.get('description') or ''}")
        else:
            print(f"{x.get('html_url')}")


def cmd_user(pos, opts):
    if not pos:
        fail("gh user <login>")
    d = api_json("GET", f"/users/{pos[0]}")
    print(d.get("name") or d.get("login"))
    if d.get("bio"):
        print(d["bio"])
    print(f"{d.get('public_repos', 0)} public repositories, {d.get('followers', 0)} followers")
    if d.get("location"):
        print(d["location"])
    print(d.get("html_url", ""))


# ---------------------------------------------------------------- writing

def cmd_token(pos, opts):
    if not pos:
        if have_token():
            print(f'a GitHub token is in the vault as "{token_item()}".')
        else:
            print(f'no GitHub token yet (I looked for "{token_item()}"). Run `gh token ask`.')
        return
    what = pos[0]
    if what == "ask":
        s = load_state()
        if opts.get("item"):
            s["token_item"] = opts["item"]
        if opts.get("domain"):
            s["token_domain"] = opts["domain"]
        save_state(s)
        exe = vault_bin()
        if not exe:
            fail("the vault command (kluis) is not on this system")
        print("The vault opens a window to paste the GitHub token; it goes straight into the vault.")
        p = subprocess.run([exe, "vraag", token_item(), "--domein", token_domain(),
                            "GitHub API token for gh (Contents, Issues and Pull requests write)"],
                           capture_output=True, text=True, timeout=200)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            fail(err or out or "the vault did not save a token")
        print(out or f'saved as "{token_item()}".')
        return
    if what == "item":
        name = opts.get("name") or (pos[1] if len(pos) > 1 else "")
        if not name:
            fail("gh token item <name> [--domain <domain>]")
        s = load_state()
        s["token_item"] = name
        if opts.get("domain"):
            s["token_domain"] = opts["domain"]
        save_state(s)
        print(f'using vault item "{name}" for {token_domain()}')
        return
    fail("gh token [ask | item <name> [--domain D]]")


def cmd_branch(pos, opts):
    require_token()
    repo = repo_of(pos, 0)
    if len(pos) < 2:
        fail("gh branch <owner/name> <branch> [--from main]")
    branch = pos[1]
    base = opts.get("from")
    if not base:
        base = api_json("GET", f"/repos/{repo}")["default_branch"]
    ref = api_json("GET", f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(base, safe='')}")
    sha = ref["object"]["sha"]
    api_json("POST", f"/repos/{repo}/git/refs", body={"ref": f"refs/heads/{branch}", "sha": sha}, token=True)
    print(f"branch {branch} created from {base} ({sha[:7]})")


def ensure_branch(repo, branch, base=None):
    """The ref sha of branch, creating it from base (or the default branch) when new."""
    status, text = request("GET", f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
    if status == 200:
        return json.loads(text)["object"]["sha"], False
    if status not in (404, 409):
        fail(github_error(status, text))
    if not base:
        base = api_json("GET", f"/repos/{repo}")["default_branch"]
    ref = api_json("GET", f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(base, safe='')}")
    sha = ref["object"]["sha"]
    api_json("POST", f"/repos/{repo}/git/refs", body={"ref": f"refs/heads/{branch}", "sha": sha}, token=True)
    return sha, True


def cmd_commit(pos, opts):
    require_token()
    repo = repo_of(pos, 0)
    if len(pos) < 4:
        fail('gh commit <owner/name> <branch> "<message>" <path>=<text|@file> ...')
    branch = pos[1]
    message = pos[2]
    pairs = []
    for item in pos[3:]:
        if "=" not in item:
            fail(f'give each file as <path>=<text|@file>, got "{item}"')
        path, value = item.split("=", 1)
        if not path:
            fail("a file needs a path in the repository")
        pairs.append((path.lstrip("/"), read_value(value)))
    parent, created = ensure_branch(repo, branch, opts.get("from"))
    base_commit = api_json("GET", f"/repos/{repo}/git/commits/{parent}")
    tree_sha = base_commit["tree"]["sha"]
    entries = []
    for path, data in pairs:
        if isinstance(data, bytes):
            blob = api_json("POST", f"/repos/{repo}/git/blobs",
                            body={"content": base64.b64encode(data).decode(), "encoding": "base64"}, token=True)
        else:
            blob = api_json("POST", f"/repos/{repo}/git/blobs",
                            body={"content": data, "encoding": "utf-8"}, token=True)
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = api_json("POST", f"/repos/{repo}/git/trees",
                    body={"base_tree": tree_sha, "tree": entries}, token=True)
    commit = api_json("POST", f"/repos/{repo}/git/commits",
                      body={"message": message, "tree": tree["sha"], "parents": [parent]}, token=True)
    api_json("PATCH", f"/repos/{repo}/git/refs/heads/{urllib.parse.quote(branch, safe='')}",
             body={"sha": commit["sha"]}, token=True)
    what = "created" if created else "on"
    print(f"committed {len(pairs)} file(s) {what} {branch}: {commit['sha'][:7]} {message}")
    print(commit.get("html_url", ""))


def cmd_pr_write(pos, opts):
    if not pos:
        fail("gh pr <create|comment> ...")
    what = pos[0]
    if what == "create":
        repo = repo_of(pos, 1)
        title = opts.get("title")
        head = opts.get("head")
        base = opts.get("base")
        if not (title and head and base):
            fail('gh pr create <owner/name> --head <branch> --base <base> --title "..." [--body "..."]')
        body = {"title": title, "head": head, "base": base, "body": opts.get("body", "")}
        if opts.get("draft"):
            body["draft"] = True
        d = api_json("POST", f"/repos/{repo}/pulls", body=body, token=True)
        print(f"pull request #{d.get('number')} opened: {d.get('title')}")
        print(d.get("html_url", ""))
        return
    if what == "comment":
        repo = repo_of(pos, 1)
        if len(pos) < 4:
            fail('gh pr comment <owner/name> <number> "<text>"')
        num = number(pos[2])
        d = api_json("POST", f"/repos/{repo}/issues/{num}/comments",
                     body={"body": pos[3]}, token=True)
        print(f"comment placed on #{num}: {d.get('html_url', '')}")
        return
    fail("gh pr <create|comment> ...")


def cmd_pr_read(pos, opts):
    repo = repo_of(pos, 0)
    if len(pos) < 2:
        fail("gh pr <owner/name> <number>")
    num = number(pos[1])
    d = api_json("GET", f"/repos/{repo}/pulls/{num}")
    print(f"#{d.get('number')} {d.get('title')}")
    who = (d.get("user") or {}).get("login", "?")
    head = (d.get("head") or {}).get("ref", "?")
    base = (d.get("base") or {}).get("ref", "?")
    print(f"{d.get('state')} {head} -> {base} by {who}")
    print(f"{d.get('commits', '?')} commits, {d.get('additions', 0)} added, {d.get('deletions', 0)} removed, {d.get('changed_files', 0)} files")
    if d.get("mergeable") is not None:
        print("mergeable" if d.get("mergeable") else "not mergeable (conflicts)")
    print(d.get("html_url", ""))
    if d.get("body"):
        print("")
        body = d["body"].strip()
        print(body[:FILE_CHARS] + ("\n... cut off" if len(body) > FILE_CHARS else ""))
    if opts.get("files"):
        f = api_json("GET", f"/repos/{repo}/pulls/{num}/files?per_page=50") or []
        print("")
        for x in f:
            print(f"{x.get('status', '?')} {x.get('filename')} (+{x.get('additions', 0)} -{x.get('deletions', 0)})")


def cmd_issue_write(pos, opts):
    if not pos:
        fail("gh issue <create|comment> ...")
    what = pos[0]
    if what == "create":
        repo = repo_of(pos, 1)
        title = opts.get("title")
        if not title:
            fail('gh issue create <owner/name> --title "..." [--body "..."] [--labels a,b]')
        body = {"title": title, "body": opts.get("body", "")}
        if opts.get("labels"):
            body["labels"] = [x.strip() for x in opts["labels"].split(",") if x.strip()]
        d = api_json("POST", f"/repos/{repo}/issues", body=body, token=True)
        print(f"issue #{d.get('number')} opened: {d.get('title')}")
        print(d.get("html_url", ""))
        return
    if what == "comment":
        repo = repo_of(pos, 1)
        if len(pos) < 4:
            fail('gh issue comment <owner/name> <number> "<text>"')
        num = number(pos[2])
        d = api_json("POST", f"/repos/{repo}/issues/{num}/comments",
                     body={"body": pos[3]}, token=True)
        print(f"comment placed on #{num}: {d.get('html_url', '')}")
        return
    fail("gh issue <create|comment> ...")


# ---------------------------------------------------------------- hooks

def cmd_hooks(pos, opts):
    repo = repo_of(pos)
    require_token()
    d = api_json("GET", f"/repos/{repo}/hooks", token=True)
    if not d:
        print(f"no webhooks on {repo}")
        return
    for x in d:
        conf = x.get("config") or {}
        events = ", ".join(x.get("events") or [])
        state = "active" if x.get("active") else "paused"
        print(f"#{x.get('id')} {state} [{events}] {mask_url(conf.get('url', ''))}")


def cmd_hook_url(pos, opts):
    if not pos:
        url = hook_url()
        print(f"house webhook: {mask_url(url)}" if url else
              "no house webhook saved yet. Make an incoming webhook on the Integrations screen, "
              "then `gh hook url <the address>`.")
        return
    url = pos[0]
    if not url.startswith("https://") and not url.startswith("http://"):
        fail("give the full address, starting with https://")
    s = load_state()
    s["hook_url"] = url
    save_state(s)
    print(f"saved the house webhook address: {mask_url(url)} (kept in this folder, not in the code)")


def events_of(opts):
    if not opts.get("events"):
        return DEFAULT_EVENTS
    return [x.strip() for x in opts["events"].split(",") if x.strip()]


def cmd_hook_add(pos, opts):
    require_token()
    repo = repo_of(pos)
    url = opts.get("url") or hook_url()
    if not url:
        fail("no house webhook address. Make one on the Integrations screen, then `gh hook url <address>`.")
    events = events_of(opts)
    d = api_json("POST", f"/repos/{repo}/hooks",
                 body={"name": "web", "active": True, "events": events,
                       "config": {"url": url, "content_type": "json", "insecure_ssl": "0"}},
                 token=True)
    print(f"webhook #{d.get('id')} added to {repo} for {', '.join(events)}: {mask_url(url)}")


def cmd_hook_rm(pos, opts):
    require_token()
    repo = repo_of(pos, 0)
    if len(pos) < 2:
        fail("gh hook rm <owner/name> <id>")
    hook_id = number(pos[1], "webhook id")
    api_json("DELETE", f"/repos/{repo}/hooks/{hook_id}", token=True)
    print(f"webhook #{hook_id} removed from {repo}")


def sample_event(event, repo):
    host = "https://github.com"
    if event == "issues":
        return {"action": "opened",
                "issue": {"number": 1, "title": "A test issue", "html_url": f"{host}/{repo}/issues/1",
                          "user": {"login": "iris"}, "state": "open"},
                "repository": {"full_name": repo, "html_url": f"{host}/{repo}"},
                "sender": {"login": "iris"}}
    if event == "pull_request":
        return {"action": "opened",
                "pull_request": {"number": 1, "title": "A test pull request", "html_url": f"{host}/{repo}/pull/1",
                                 "user": {"login": "iris"}, "state": "open",
                                 "head": {"ref": "test"}, "base": {"ref": "main"}},
                "repository": {"full_name": repo, "html_url": f"{host}/{repo}"},
                "sender": {"login": "iris"}}
    return {"ref": "refs/heads/main", "before": "0" * 40, "after": "1" * 40,
            "repository": {"full_name": repo, "html_url": f"{host}/{repo}"},
            "pusher": {"name": "iris"},
            "commits": [{"id": "1" * 40, "message": "A test commit"}]}


def send_event(event, repo, data, url=None):
    url = url or hook_url()
    if not url:
        fail("no house webhook address. Make one on the Integrations screen, then `gh hook url <address>`.")
    payload = data if data is not None else sample_event(event, repo)
    status, text = direct("POST", url,
                          {"Content-Type": "application/json", "User-Agent": UA, "X-GitHub-Event": event},
                          json.dumps(payload).encode("utf-8"))
    if status >= 400:
        fail(f"the house webhook answered {status}: {text[:200]}")
    print(f"sent a {event} event for {repo} to the house webhook (status {status}).")


def cmd_hook_test(pos, opts):
    event = opts.get("event", "push")
    repo = opts.get("repo") or default_repo() or "octocat/Hello-World"
    send_event(event, repo, None, opts.get("url"))


def cmd_hook_send(pos, opts):
    if not pos:
        fail('gh hook send <event> [--data "<json>"] [--url <address>]')
    event = pos[0]
    data = None
    if opts.get("data"):
        data = read_value(opts["data"]) if opts["data"].startswith("@") else opts["data"]
        try:
            data = json.loads(data)
        except ValueError:
            fail("--data must be JSON")
    repo = opts.get("repo") or default_repo() or "octocat/Hello-World"
    send_event(event, repo, data, opts.get("url"))


# ---------------------------------------------------------------- custom api

def cmd_api(pos, opts):
    if not pos:
        fail('gh api <path-or-url> [--method ...] [--body "..."] [--header "K: V"] [--token]')
    path = pos[0]
    headers = {}
    for h in opts.get("header", []):
        if ":" not in h:
            fail(f'--header expects "Name: value", got "{h}"')
        name, value = h.split(":", 1)
        headers[name.strip()] = value.strip()
    body = opts.get("body")
    if body == "-":
        body = sys.stdin.read()
    elif body and body.startswith("@"):
        body = read_value(body)
    method = (opts.get("method") or ("POST" if body else "GET")).upper()
    status, text = request(method, path, body=body, token=bool(opts.get("token")), headers=headers)
    if status >= 400:
        print(f"status {status}")
        print(text[:2000])
        sys.exit(1)
    try:
        print(json.dumps(json.loads(text), indent=2, ensure_ascii=False))
    except ValueError:
        print(text)


# ---------------------------------------------------------------- dispatch

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("help", "--help", "-h"):
        print(__doc__.strip())
        return
    cmd = args[0]
    rest = args[1:]

    if cmd == "repo":
        cmd_repo(*parse(rest))
    elif cmd == "default":
        cmd_default(*parse(rest))
    elif cmd == "file":
        cmd_file(*parse(rest, valued=("ref",)))
    elif cmd == "tree":
        cmd_tree(*parse(rest, valued=("ref",)))
    elif cmd == "issues":
        cmd_issues(*parse(rest, valued=("state", "limit", "label")))
    elif cmd == "issue":
        if rest and rest[0] in ("create", "comment"):
            cmd_issue_write(*parse(rest, valued=("title", "body", "labels")))
        else:
            cmd_issue(*parse(rest, flags=("comments",)))
    elif cmd == "prs":
        cmd_prs(*parse(rest, valued=("state", "limit")))
    elif cmd == "pr":
        if rest and rest[0] in ("create", "comment"):
            cmd_pr_write(*parse(rest, valued=("title", "body", "head", "base"), flags=("draft",)))
        else:
            cmd_pr_read(*parse(rest, flags=("files",)))
    elif cmd == "commits":
        cmd_commits(*parse(rest, valued=("ref", "limit")))
    elif cmd == "branches":
        cmd_branches(*parse(rest))
    elif cmd == "releases":
        cmd_releases(*parse(rest, valued=("limit",)))
    elif cmd == "search":
        cmd_search(*parse(rest, valued=("type", "limit")))
    elif cmd == "user":
        cmd_user(*parse(rest))
    elif cmd == "token":
        cmd_token(*parse(rest, valued=("item", "domain", "name")))
    elif cmd == "branch":
        cmd_branch(*parse(rest, valued=("from",)))
    elif cmd == "commit":
        cmd_commit(*parse(rest, valued=("from",)))
    elif cmd == "hooks":
        cmd_hooks(*parse(rest))
    elif cmd == "hook":
        if not rest:
            fail("gh hook <url|add|rm|test|send> ...")
        sub = rest[0]
        if sub == "url":
            cmd_hook_url(*parse(rest[1:]))
        elif sub == "add":
            cmd_hook_add(*parse(rest[1:], valued=("url", "events")))
        elif sub == "rm":
            cmd_hook_rm(*parse(rest[1:]))
        elif sub == "test":
            cmd_hook_test(*parse(rest[1:], valued=("event", "repo")))
        elif sub == "send":
            cmd_hook_send(*parse(rest[1:], valued=("data", "url", "repo")))
        else:
            fail(f"unknown hook command {sub!r}")
    elif cmd == "api":
        cmd_api(*parse(rest, valued=("method", "body"), repeated=("header",), flags=("token",)))
    else:
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
