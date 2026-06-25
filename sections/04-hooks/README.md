# 4 · Hooks

> Hook around the loop, never rewrite the loop.

Hooks are user-configured callbacks that fire at fixed points in the agent cycle: before a tool runs, after it runs, when a prompt is submitted, when the session starts or stops. They let you log, gate, modify, or inject without touching the `while` (section 1). The loop stays a stable core; extensions clip onto the outside.

---

## Problem

Every new behavior you want (log each bash call, auto `git add` after edits, validate input, block a dangerous command) is a temptation to edit the loop body. Do that a few times and the loop is unrecognizable: permission checks, logging, and notifications all tangled into the four numbered steps. The thing you wanted to extend was the agent's behavior, but the thing you changed was the loop itself.

Leave hooks out and there is no way to extend the agent except by forking the loop, so every site that wants a side effect rewrites the core.

---

## Mechanism

A small `Hooks` object maps event names to callback lists. The loop never calls a check directly; `_dispatch` calls `fire_pre` before the gate and `fire_post` after a run, and the callbacks decide what happens. A PreToolUse callback can block the call or rewrite its input.

### New: hooks

```python
class Hooks:                                     # src/hooks.py
    def fire_pre(self, name, args):               # PreToolUse: block or rewrite
        for fn in self._hooks["PreToolUse"]:
            out = fn(name, args) or {}
            if out.get("updated_args"): args = out["updated_args"]
            if out.get("deny"):         return True, args, out.get("message", "")
        return False, args, ""
    def fire_post(self, name, args, result):      # PostToolUse: observe
        for fn in self._hooks["PostToolUse"]: fn(name, args, result)
```

- `on(event, fn)` registers a callback; `fire_pre` runs the PreToolUse list (one returning `{'deny': True}` blocks, `{'updated_args': ...}` rewrites); `fire_post` runs the PostToolUse observers.

### How it integrates

Two fire points are the only change to `_dispatch` ([`src/loop.py`](src/loop.py)) vs section 3: PreToolUse before the gate, PostToolUse after a successful run.

```python
# src/loop.py _dispatch
blocked, args, msg = hooks.fire_pre(name, args)          # 4 · PreToolUse
if blocked: return res(msg)
decision = permissions.decide(tool, mode, allow_rules)   # 3 · gate (section 3)
...                                                      # deny / ask short-circuit
out = res(run_tool(tool, args))                          # 2 · execute -> tool_result
hooks.fire_post(name, args, out)                         # 4 · PostToolUse
```

- A blocked or denied call never reaches `run_tool` or PostToolUse.
- Hooks compose with the gate, they do not replace it. A PreToolUse hook can tighten the decision (`deny` or `ask`) but never loosen it: a hook's `allow` cannot override a rule-based `deny`/`ask` (Claude Code reconciles the two in `resolveHookPermissionDecision`). The demo's PreToolUse hook blocks `rm -rf` even under `bypassPermissions`.

Claude Code's lifecycle hooks are config-driven (`.claude/settings.json`), not source edits. The event set lives in `HOOK_EVENTS` (`entrypoints/sdk/coreTypes.ts`, 27 events). A hook returns a `HookResult` (`types/hooks.ts`) whose fields decide the outcome: `permissionBehavior` (`allow`/`deny`/`ask`/`passthrough`), `updatedInput` (rewrite the tool's arguments), `additionalContext` (inject text), `preventContinuation` (stop the loop gracefully), `blockingError` (feed an error back so the model self-corrects).

Note the distinction: this section is the *lifecycle* hook system. The many React render hooks in the `hooks/` folder (e.g. `costHook.ts`'s `useCostSummary`) are unrelated UI plumbing that happen to share the word.

---

## Per system

How each agent exposes interception points around the loop.

| System | Hook events | Fire point | Can block / modify? |
|---|---|---|---|
| **Claude Code** | 27 in `HOOK_EVENTS` (`coreTypes.ts`): `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `SessionStart`, `SessionEnd`, `Stop`, `SubagentStart`/`SubagentStop`, `PreCompact`/`PostCompact`, `Setup`, etc. | config-driven from `.claude/settings.json`, snapshotted once at `setup.ts` via `captureHooksConfigSnapshot()`; `PreToolUse` fires before the permission gate (`toolExecution.ts` runs `runPreToolUseHooks` then `resolveHookPermissionDecision`) | yes · `HookResult` (`types/hooks.ts`): `permissionBehavior` to deny/ask, `updatedInput` to rewrite args, `preventContinuation` to stop, `blockingError` to make the model retry |
| *(more soon)* | | | |

> **Trade-off:** config-driven hooks fired at fixed points buy extension without forking the loop (anyone can add a gate or a side effect via `settings.json`), but the fixed event set is the ceiling. You can only intercept where a hook event exists, and a hook returning `allow` still cannot override a `deny`/`ask` rule (`resolveHookPermissionDecision` in `toolHooks.ts` enforces that hooks never widen permission). Power within the seams, none outside them.

---

## Failure modes

- **Hook used to bypass permissions.** A `PreToolUse` hook returns `allow` for a tool the user denied. Claude Code blocks this: `resolveHookPermissionDecision` (`toolHooks.ts`) still runs `checkRuleBasedPermissions`, so a hook `allow` cannot defeat a `settings.json` `deny`/`ask` (section 3). Without this invariant, a config callback becomes a permission hole.
- **Stop hook never lets the agent stop.** A `Stop` hook that always returns a `blockingError` makes the model self-correct, which retriggers the Stop hook, forever. Mitigated by the `stopHookActive` flag (`query/stopHooks.ts`): once a stop hook has fired, the next iteration carries the flag so it does not fire again.
- **Hidden hook swapped mid-session.** If hook config were re-read live, a process could edit `settings.json` after launch to inject a callback. Mitigated by snapshotting config once at startup (`captureHooksConfigSnapshot` in `setup.ts`) so the active hook set is frozen.
- **Slow or hung hook stalls the loop.** A hook shells out to a slow command and the agent waits. Hooks carry a `timeout` (`HookCallback.timeout` in `types/hooks.ts`) and can run `async`, so a misbehaving hook is bounded rather than blocking the run.
- **PostToolUse silently halts work.** A `PostToolUse` hook returning `preventContinuation: true` stops the loop via a `hook_stopped_continuation` attachment (`toolHooks.ts`). Intended as graceful completion, but if misconfigured it looks like the agent quitting early (section 1).

---

## Runnable

[`src/`](src/) carries 03 forward and adds interception. New: [`hooks.py`](src/hooks.py) (PreToolUse / PostToolUse). Updated: [`loop.py`](src/loop.py) fires hooks around each call. [`test.py`](src/test.py) shows a PreToolUse hook blocking `rm -rf` even under `bypassPermissions`.

```bash
python sections/04-hooks/src/test.py         # offline checks, no key
uv run python sections/04-hooks/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code structure: `types/hooks.ts` (`HookResult`, `HookCallback`, hook event schemas), `entrypoints/sdk/coreTypes.ts` (`HOOK_EVENTS`), `services/tools/toolHooks.ts` (`resolveHookPermissionDecision`, `hook_stopped_continuation`), `query/stopHooks.ts` (`stopHookActive`, `handleStopHooks`), `services/tools/toolExecution.ts` (`runPreToolUseHooks` before `resolveHookPermissionDecision`), `setup.ts` (`captureHooksConfigSnapshot`), `costHook.ts` (the contrasting React render hook).
- Framing: learn-claude-code · s04_hooks

Educational reconstruction from public structure and observed behavior, not an official description of any system.
