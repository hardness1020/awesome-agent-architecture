# 3 · Permission & sandbox

> Set boundaries first, then grant freedom. A gate between the model's request and the world.

The model asks to run a tool; this section decides whether it may. It sits on step 3 of the loop (section 1), between the tool request and execution, classifying each call as allow, ask, or deny, and optionally running side effects inside a sandbox so a mistake is contained.

---

## Problem

A tool runtime that runs whatever the model emits is a remote shell with no operator. The model can hallucinate, get prompt injected, or simply be wrong, and a single `Bash` call can delete files, leak secrets, or push to prod. Trust in the model is not a safety boundary; code is.

So something must:

1. Inspect each tool call before it runs.
2. Decide allow, ask, or deny from rules plus context.
3. Pause for a human when the call is risky and not pre-authorized.
4. Contain the blast radius when a call does run.

Leave it out and the agent is one bad token away from an irreversible side effect, with no human in the loop and no way to undo.

---

## Mechanism

A pure function decides before execution: given the tool, the current permission **mode**, and any pre-approved rules, it returns `allow`, `ask`, or `deny`. The mode shifts the defaults. An `ask` pauses the loop for a human; a `deny` never runs; an `allow` proceeds (and a real `Bash` can still run inside a sandbox so even an allowed command is confined).

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

- Pure: tool plus mode plus rules into `allow` / `ask` / `deny`. No I/O, so the demo asserts it mode by mode.

### How it integrates

One gate call goes into `_dispatch` (`src/loop.py`, the section-2 dispatcher), just before `run_tool`:

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

- The loop body from sections 1 and 2 is untouched; only `_dispatch` gains the gate. `res` wraps content as a `tool_result` block keyed to `block.id`.
- `deny` and an unapproved `ask` never reach `run_tool`. `_dispatch` returns a `res(...)` result into `messages[]` like any tool result, so the model sees the denial on its next turn and adapts. `approver` (the human) defaults to `False`, so `ask` means `no` unless the call is approved (plan approval, section 5).
- Net: the gate substitutes a result for an action at step 3, so every call still yields a result and section 1's append-and-continue invariant holds.

This is the gate the bare loop deliberately omitted. Real systems extend it with ordered rule sources, remembered approvals, and a sandbox (see Per system).

---

## Per system

How each agent gates side effects, switches posture, and remembers decisions.

| System | Gate point | Permission modes | Sandbox | Rule persistence |
| --- | --- | --- | --- | --- |
| **Claude Code** | `canUseTool` (`QueryEngine.ts`), before each tool runs | `default`, `acceptEdits`, `plan`, `bypassPermissions`, `dontAsk` (+ internal `auto`, `bubble`) | `Bash` via `shouldUseSandbox.ts` + `SandboxManager`; `dangerouslyDisableSandbox` opts out | 8 ordered rule sources; `destination` `session` or settings files |
| *(more soon)* | | | | |

### Claude Code

- **Gate per call.** The loop (`QueryEngine.ts`) calls `canUseTool` for every tool use; `useCanUseTool.tsx` resolves a `PermissionDecision` (`allow` / `deny` / `ask`) from `hasPermissionsToUseTool`.
- **Modes are strings.** `types/permissions.ts` sets `EXTERNAL_PERMISSION_MODES = ['acceptEdits','bypassPermissions','default','dontAsk','plan']`.
- **8 rule sources, priority-merged.** `userSettings`, `projectSettings`, `localSettings`, `flagSettings`, `policySettings`, `cliArg`, `command`, `session`.
- **Approvals persist.** Saved with `destination: 'session'` or to a settings file via `PermissionUpdate.ts`, so "always allow" sticks.
- **WebFetch has its own gate.** `tools/WebFetchTool/preapproved.ts` lets `GET`s to a fixed `PREAPPROVED_HOSTS` set (docs sites) through; the sandbox deliberately does not inherit that list.
- **MCP and remote.** MCP servers get a separate approval step (`services/mcpServerApproval.tsx`); remote runs bridge the prompt back to a local terminal (`remote/remotePermissionBridge.ts`).

> **Trade-off:** ordered rules plus modes plus a sandbox give fine-grained, auditable control and let trusted work flow without friction, but the surface is large (8 rule sources, several modes, a sandbox adapter) and every escape hatch (`bypassPermissions`, `dangerouslyDisableSandbox`, preapproved hosts) is a place safety can leak. Fewer knobs are safer to reason about; more knobs are friendlier to power users.

---

## Failure modes

- **Pattern-match bypass.** Deny lists keyed on substrings miss command variants and shell expansion (`FOO=bar rm`, wrappers, `&&` chains). Mitigation: gate on behavior and confinement, not strings; Claude Code strips leading env vars and safe wrappers to a fixed point before matching, and treats the sandbox (not string matching on `Bash`) as the real boundary (section 2).
- **Mode left wide open.** `bypassPermissions` or a broad `allow` rule turns the gate off, and a later risky call runs silently. Mitigation: scope bypass to the session, surface the active mode, keep ask rules non-bypassable.
- **Over-prompting fatigue.** Asking on every call trains users to approve blindly. Mitigation: `acceptEdits` for low-risk edits, preapproved hosts, and remembered `session` rules, without auto-approving destructive calls.
- **Silent denial in delegation.** A subagent (section 6) that denies on its own has no human to ask. Mitigation: Claude Code's internal `bubble` mode floats the prompt up to the parent's terminal instead of failing quietly.
- **Sandbox escape or unavailability.** A disabled sandbox or an opt-out (`dangerouslyDisableSandbox`) sends an allowed call straight to the host. Mitigation: gate the opt-out behind policy (`areUnsandboxedCommandsAllowed`) and keep the permission prompt as the backstop.

---

## Runnable

[`src/`](src/) carries 02 forward and adds:

- [`permissions.py`](src/permissions.py): `decide` over the four modes (the gate).
- [`loop.py`](src/loop.py): gates each call in `_dispatch` before running it.

```bash
python sections/03-permission-sandbox/src/test.py         # offline checks, no key
uv run python sections/03-permission-sandbox/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `QueryEngine.ts`, `hooks/useCanUseTool.tsx`, `types/permissions.ts`, `tools/BashTool/shouldUseSandbox.ts`, `tools/WebFetchTool/preapproved.ts`, `utils/permissions/PermissionUpdate.ts`.
- learn-claude-code · s03_permission: section framing.
