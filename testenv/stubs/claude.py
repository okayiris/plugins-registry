#!/usr/bin/env python3
"""A stand-in for the Claude Code CLI (`claude`), for the claude-code plugin's scenario.

  claude --version                     a version
  claude auth status --json            signed in when SIM_CLAUDE_LOGIN is not "off"
  claude -p <prompt> --output-format json [--tools ...] [--resume <id>] ...
                                       one JSON result, like the real one, that repeats what it was given:
                                       the prompt, the folder, the tools and the session it resumed.

A prompt with "use bash" asks for Bash; without Bash among the tools that comes back as a permission denial.
Every call is written to $HOME/.sim-claude-log, so a test can check how the plugin called Claude Code.
"""
import json
import os
import sys
import uuid


def flag(args, name, many=False):
    if name not in args:
        return None
    i = args.index(name) + 1
    if not many:
        return args[i] if i < len(args) else None
    out = []
    while i < len(args) and not args[i].startswith("--"):
        out.append(args[i])
        i += 1
    return out


def main(args):
    with open(os.path.join(os.environ.get("HOME", "."), ".sim-claude-log"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"args": args, "cwd": os.getcwd(), "config": os.environ.get("CLAUDE_CONFIG_DIR")}) + "\n")
    if args[:1] == ["--version"]:
        print("2.1.0 (Claude Code)")
        return
    if args[:2] == ["auth", "status"]:
        on = os.environ.get("SIM_CLAUDE_LOGIN", "on") != "off"
        print(json.dumps({"loggedIn": on, "authMethod": "claude.ai" if on else "none", "apiProvider": "firstParty"}))
        return
    if "-p" not in args:
        sys.exit("claude stub: only -p, --version and auth status")
    prompt = flag(args, "-p")
    tools = (flag(args, "--tools") or "").split(",")
    resumed = flag(args, "--resume")
    session = resumed or str(uuid.UUID(int=len(prompt) * 7919))
    denials = []
    if "use bash" in prompt.lower() and "Bash" not in tools:
        denials.append({"tool_name": "Bash", "tool_use_id": "toolu_1", "tool_input": {"command": "npm test"}})
    result = (f"Looked at {os.path.basename(os.getcwd())} for: {prompt}. Tools: {', '.join(tools)}."
              + (f" Went on from session {resumed[:8]}." if resumed else ""))
    if "long answer" in prompt.lower():
        result += "\n" + "\n".join(f"Line {i} of a long answer." for i in range(1, 120))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": result,
                      "session_id": session, "num_turns": 3, "total_cost_usd": 0.0412,
                      "permission_denials": denials}))


if __name__ == "__main__":
    main(sys.argv[1:])
