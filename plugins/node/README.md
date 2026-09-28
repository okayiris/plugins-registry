# Node

Run commands on your own computer or server from chat, without approving each one.

A **node** is a machine you own: your Mac, a Linux server, a Raspberry Pi. You install a small agent on it
and pair it once with a key from the house. From then on the agent keeps a connection open to the bridge,
and Iris can run a command there and read the output back. The pairing is the approval; there is no prompt
per command and no prompt per hour. You can break the pairing at any time, from either side.

```
you:    nodes pair
Iris:   Pairing key for 'mac-studio' (works once, valid 10 minutes).
        <key>
        ...
```

## Install on the device

`nodes pair` prints these steps with the right address and key filled in:

```sh
curl -fsSL <bridge>/node/agent -o /tmp/iris-node-agent.py
python3 /tmp/iris-node-agent.py pair --bridge <bridge> --key <key>
python3 /tmp/iris-node-agent.py install
```

`install` keeps the agent running as a service: a `launchd` user agent on macOS, a `systemd --user` unit on
Linux. It starts now and again at every login. Remove it with `node-agent.py uninstall`.

The agent needs Python 3 (already present on macOS and most Linux systems). It stores its paired secret in
`~/.iris-node/config.json`, readable only by you (`mode 600`). It never prints the secret.

## Commands in the house

| command | what it does |
| --- | --- |
| `nodes` | list paired nodes and waiting pairing keys |
| `nodes pair [label]` | make a pairing key for a new device and print the install steps |
| `nodes run "<name>" "<command>" [--timeout N] [--cwd DIR]` | run a command on that node and show the output |
| `nodes revoke "<name>"` | break the pairing; the device stops within a second |
| `nodes key rm "<label>"` | throw away a pairing key that was never used |
| `nodes status "<name>"` | one node, with its os, host and last contact |

On the device itself:

```sh
node-agent.py run        # the permanent connection
node-agent.py status     # what it is paired to, and whether the bridge still knows it
node-agent.py revoke     # unpair from this side and drop the key
```

## Permissions

**internet** - the command talks to the bridge; the agent talks to the bridge. Nothing else.

The agent itself needs no special rights. It refuses to run as root unless you explicitly allow it in its
config, and it runs commands through your own login shell, so your `PATH` is what you expect.

## Security

- **Pairing is the only approval.** A pairing key is 32 random hex characters, valid for ten minutes, and
  works exactly once. It is stored on the bridge as a hash, never in the clear.
- **The device gets a long-lived secret** (32 random bytes) after pairing. The bridge stores only its
  SHA-256 hash. The secret is in `~/.iris-node/config.json`, `mode 600`.
- **Outbound only.** The device holds a long poll open to the bridge. No open port, no inbound NAT, no
  firewall change on the device.
- **Revocation is immediate.** `nodes revoke "<name>"` deletes the pairing on the bridge, refuses the open
  poll with `401`, and fails commands still in flight. The agent sees the `401` and stops. `node-agent.py
  revoke` does the same from the device side.
- **Limits.** A command times out (default 60 s, at most 600 s), output is capped (256 KB) and the agent
  can refuse anything not on its `--allow` list or on its `--deny` list. For a machine that should only
  serve a few tools, pair it with `--allow "git,ls,cat"`. With an allow list set, every part of a chained
  command (`;`, `|`, `&&`) has to match and command substitution is refused, so `git status` passes but
  `git; curl evil` does not.
- Use `https://` for the bridge address the device uses. With plain `http://` the secret and every command
  travel unencrypted; the agent warns if you pair over plain http with a non-local address.

## Bridge side

The agent speaks a small protocol under `/node`:

| route | auth | purpose |
| --- | --- | --- |
| `POST /node/pair` | pairing key | exchange a one-time key for a long-lived secret |
| `GET /node/next` | node secret | long-poll for the next command (204 when idle) |
| `POST /node/result` | node secret | send stdout, stderr, exit code and timing back |
| `POST /node/bye` | node secret | unpair from the device side |
| `GET /node/me` | node secret | who the bridge thinks this node is |
| `GET /node/agent` | none | the agent source, for the one-line install |
| `GET /node` | house key | list nodes and waiting keys |
| `POST /node/key` | house key | make a pairing key |
| `POST /node/key/rm` | house key | cancel a pairing key |
| `POST /node/run` | house key | hand a command to a node and wait for the result |
| `POST /node/revoke` | house key | break a pairing |

`bridge-node.ts` in this folder is the bridge half: it keeps the node list in `DATA/nodes.json`, serves the
agent, and does the long-poll hand-off. Wire it into `src/voice.ts` next to the other route handlers:

```ts
import { nodeRoute } from "./node";
// ...
if (nodeRoute(req, res, (r) => telefoonSleutelKlopt(r))) return;
```

`nodeRoute` returns `false` for anything outside `/node`, so it composes with the existing routes. It can
also run on its own (`node bridge-node.ts --port 8799`) and that is how the bundled test drives it.

Environment variables: `NODE_DATA` (state folder, default `~/.iris-node-bridge`), `NODE_AGENT_FILE`
(path to `node-agent.py`), `NODE_PUBLIC_URL` (the address a device should use; shown by `nodes pair`),
`NODE_POLL_MS`, `NODE_KEY_TTL_MS`, `NODE_OFFLINE_MS`, `NODE_MAX_OUTPUT`.

## Test

`test_node.py` starts `bridge-node.ts` standalone, pairs a real agent, runs commands through `nodes.py`,
and checks the allow list, the timeout, a reused key, an unknown key and revocation:

```sh
python3 test_node.py
```

## Notes

- The plugin is called `node`; its command is `nodes` so it does not shadow the `node` runtime.
- Everything lives in one folder. The plugin folder itself holds no state; the bridge and the device do.
- Without a bridge that answers the `/node` routes, `nodes pair` reports that the bridge is not reachable.
