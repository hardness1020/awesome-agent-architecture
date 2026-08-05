# 3 · Permission & sandbox

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> Check each action before it reaches the system.

The model can ask to run any enabled tool. The permission layer decides whether that call may run.

A tool runtime without permissions is close to an unattended remote shell.

A bad tool call can delete files, leak secrets, or push the wrong code. Trusting the model is not a safety boundary. Code must check the request before execution.

The danger has a shape. Three capabilities together turn a helpful agent into an exfiltration tool: access to private data,
exposure to untrusted content, and the ability to communicate externally. Any two are survivable. All three at once mean that
text the agent merely reads can steer it into opening a secret and posting it somewhere. This is the lethal trifecta.

Persistent memory adds a fourth axis. A poisoned instruction written into a memory file (section 9) is read back in the next session,
so one injection keeps paying out after the session that carried it is gone.

The gate cannot remove those capabilities. An agent that reads nothing and reaches nothing does no work. What the gate can do is
put a decision in front of the calls that complete the trio, and a sandbox behind the ones it allows.

The permission layer must:

1. Inspect each tool call before it runs.
2. Decide `allow`, `ask`, or `deny`.
3. Ask a human when a risky call is not pre-approved.
4. Limit damage when a call does run.

Without this layer, one bad tool call can cause an irreversible side effect.

---

## Mechanism

![Mechanism diagram](assets/03-permission-and-sandbox.png)

A pure function makes the permission decision. It reads the tool, the current mode, and any allow rules. It returns one of three values:

- `allow`: run the tool.
- `ask`: pause and ask a human.
- `deny`: do not run the tool.

The mode changes the default behavior. For example, plan mode allows read-only tools but denies edits until the plan is approved.

### New: the gate

`decide()` is the whole permission decision:

```python
def decide(tool, mode, allow_rules) -> str:      # src/permissions.py (new)
    if mode == BYPASS:                            # operator opted out
        return "allow"
    if mode == PLAN:                              # exploring, not acting yet
        if tool.is_read_only:           return "allow"
        if tool.name == "ExitPlanMode": return "ask"     # approval handshake (section 5)
        return "deny"                             # no side effects until approved
    if tool.is_read_only or tool.name in allow_rules:
        return "allow"
    if mode == ACCEPT_EDITS and tool.is_edit:
        return "allow"                            # a class of work pre-approved
    return "ask"                                  # default: when unsure, ask
```

The function has no I/O. That makes it easy to test mode by mode.

### How it integrates

The gate runs inside `_dispatch`, just before `run_tool`:

```python
def _dispatch(block, registry, mode, allow_rules, approver):   # src/loop.py
    ...                                                  # resolve tool (section 2)
    decision = decide(tool, mode, allow_rules)           # 3 · the gate, the new line
    if decision == "deny":
        return res(f"{name} not allowed in {mode} mode")
    if decision == "ask" and not approver(name, block.input):
        return res(f"{name} denied by user")
    return res(run_tool(tool, block.input))              # only now does it run
```

- The loop body is unchanged from sections 1 and 2.
- Only `_dispatch` gains the gate.
- `deny` and unapproved `ask` never reach `run_tool`.
- The denial still returns as a `tool_result`, so the model sees what happened and can adapt.
- `approver` defaults to `False`, so `ask` means no unless the human approves.

The key invariant stays intact: every tool call produces a result message, even when the real action did not run.

Real systems add rule priority, remembered approvals, and sandboxed execution. Those are extensions of the same gate.

The next three parts describe such extensions. They come from one book's account of production coding agents, not from source this repo reads.
Treat them as a described design, not as confirmed behavior of the systems in the table below.

### Reading the command, not matching it

`decide()` gates by tool name. A shell tool needs more, because one name covers every program on the machine.
A deny list of strings is the usual first attempt, and it loses. `rm -rf /` is easy to match. `find . -exec rm {} \;` hides
the delete inside a flag. `$(echo rm) -rf /` hides it inside a substitution. `curl -o /etc/crontab` never spells `write` at all.

A semantic parser closes those gaps. It splits the command into programs and arguments, applies each program's rules for which flags
consume a value, and asks what the resolved call does. `-exec` carries a subcommand, so the subcommand gets gated too.
`-o` names a write target, so that path gets gated as a write. The check runs on meaning, not on spelling.

The same reasoning extends from the command to the goal. A destructive shortcut can still produce a correct end state: drop the table
and recreate it, delete the directory and clone it again. A result check (section 21) approves that, because it only reads the outcome.
So the gate constrains the path as well. Some actions stay blocked even when the result they would produce passes verification.

### What the sandbox actually limits

The gate decides. The sandbox bounds what a wrong decision costs. Three dimensions carry most of that weight.

- **Egress.** Deny network by default and route allowed traffic through a proxy that holds a host allowlist.
  This is the one leg of the trifecta a harness can cut cheaply. The agent still reads code and still writes files. It just cannot post them out.
- **Mounts.** Mount source read-only. Mount credential files nowhere. Give one writable workspace and nothing else.
  A secret that never enters the visible filesystem cannot be read out of it.
- **Quotas.** Cap CPU, memory, disk, and wall clock. When a cap trips, return a structured error as the tool result instead of killing the
  process silently. The model then reads a timeout and can shorten the command. A silent kill leaves it guessing.

### Keeping the ask path fast

An `ask` decision already costs a human turn. A slow decision adds a second wait in front of it, while the user watches nothing happen and
the harness works out whether it even needs to ask. A speculative check hides that wait. The harness starts the permission check in the
background and immediately shows progress that has no side effect. If the check resolves to `allow` first, the call runs and no prompt appears.
Only a check that cannot decide fast is promoted into a confirm prompt.

The safety property holds because the speculative branch never runs the tool. It runs the decision.

---

## Per system

How each agent gates side effects, changes modes, and remembers decisions.

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | Modes, ordered rules, and sandboxing give precise control. | Auditable in minutes. A rejection feeds back to the model, so the loop keeps running. |
| **Cons** | Many states to reason about. Each bypass or preapproval path must stay visible and narrow. | Treats every command the same and remembers nothing. |
| **Why** | Asking on every call breeds approval fatigue, so approvals can be remembered. | One prompt plus a regex list is enough when the environment limits the damage. |
| **How: gate point** | Before each tool runs. Web, MCP, and remote runs have their own gates. | Before a step's commands execute. Enter approves, a typed comment rejects. |
| **How: permission modes** | Default, edit-approved, plan, deny, and bypass, plus internal modes. | `human`, `confirm`, and `yolo`. Slash commands switch them at runtime. |
| **How: sandbox** | Bash can run inside a sandbox. | The environment class is the sandbox, picked per run: host, throwaway container, or wrappers on shared hosts. |
| **How: rule persistence** | Rules merge by priority from many sources, saved to the session or settings. | Whitelist regexes in config only. Matches skip the confirm prompt. |

---

## Failure modes

- **Pattern-match bypass.** String deny lists miss shell variants. Parse the command and gate what it resolves to, then keep a sandbox behind the parser.
- **Mode left too open.** A broad allow rule or bypass mode can let later risky calls run silently. Scope bypasses and surface the active mode.
- **Approval fatigue.** Asking on every call trains users to approve without reading. Preapprove low-risk classes, but keep destructive actions explicit.
- **Silent denial in a subagent.** A child agent may have no terminal to ask through. Bubble the prompt to the parent instead of failing quietly.
- **Sandbox disabled.** If an allowed command runs outside the sandbox, the permission prompt is the last check. Gate any unsandboxed path behind policy.
- **Exfiltration through approved calls.** Every call can pass the gate on its own and the session can still read a secret and send it out.
  Deny egress by default so the trio never closes.
- **Verified but destructive.** Delete and rebuild passes a result check, because the end state is right. Gate the action, not only the outcome.
- **Poisoned memory.** An instruction injected into a memory file replays in every later session. Treat stored memory as untrusted content, never as an operator rule.

---

## Runnable

[`src/`](src/) carries 02 forward and adds:

- [`permissions.py`](src/permissions.py): `decide` over the four modes.
- [`loop.py`](src/loop.py): gates each call in `_dispatch` before running it.

```bash
python sections/03-permission-sandbox/src/test.py         # offline checks, no key
uv run python sections/03-permission-sandbox/src/demo.py  # live demo, needs a key
```

---

## Sources

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code):
  `QueryEngine.ts`, `hooks/useCanUseTool.tsx`, `types/permissions.ts`, `utils/permissions/PermissionUpdate.ts`.
- [Claude Code sandbox and web gates](https://github.com/yasasbanukaofficial/claude-code): `tools/BashTool/shouldUseSandbox.ts`, `tools/WebFetchTool/preapproved.ts`.
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent): `agents/interactive.py`, `environments/docker.py`, `environments/extra/bubblewrap.py`.
- [ai-agent-book · chapter 5](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter5.md) (《深入理解 AI Agent》, 李博杰; the Chinese original is canonical):
  the memory amplification axis, sandbox egress, mount and quota policy, semantic command parsing, speculative permission checks,
  and constraining the path instead of only the result. Single source for those designs.
- [The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (Simon Willison):
  private data access, untrusted content, and external communication as the three capabilities that must not combine.
- [learn-claude-code · s03_permission](https://github.com/shareAI-lab/learn-claude-code): section framing.
