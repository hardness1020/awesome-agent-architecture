# 4 · Hooks

> Hook around the loop, never rewrite the loop.

Hooks are user-configured callbacks that fire at fixed points in the agent cycle: before a tool runs, after it runs, when a prompt is submitted, when the session starts or stops. They let you log, gate, modify, or inject without touching the `while` (section 1): the loop stays a stable core, extensions clip onto the outside. Every new behavior you want (log each bash call, auto `git add` after edits, validate input, block a dangerous command) is otherwise a temptation to edit the loop body. Do that a few times and the loop is unrecognizable: permission checks, logging, and notifications all tangled into the four numbered steps. The thing you wanted to extend was the agent's behavior, but the thing you changed was the loop itself.

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
| --- | --- | --- | --- |
| **Claude Code** | 27 in `HOOK_EVENTS` (`coreTypes.ts`) | config-driven from `.claude/settings.json`, snapshotted at startup; `PreToolUse` fires before the permission gate | yes · `HookResult` (`types/hooks.ts`): `permissionBehavior`, `updatedInput`, `preventContinuation`, `blockingError` |
| *(more soon)* | | | |

### Claude Code

- **Events.** 27 in `HOOK_EVENTS` (`coreTypes.ts`): `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `SessionStart`, `SessionEnd`, `Stop`, `SubagentStart`/`SubagentStop`, `PreCompact`/`PostCompact`, `Setup`, and more.
- **Config-driven, frozen.** Loaded from `.claude/settings.json`, snapshotted once via `captureHooksConfigSnapshot()` (`setup.ts`), not source edits.
- **Fire order.** `toolExecution.ts` runs `runPreToolUseHooks` then `resolveHookPermissionDecision`, so `PreToolUse` lands before the permission gate (section 3).

> **Trade-off:** config-driven hooks fired at fixed points buy extension without forking the loop (anyone can add a gate or a side effect via `settings.json`), but the fixed event set is the ceiling. You can only intercept where a hook event exists, and a hook returning `allow` still cannot override a `deny`/`ask` rule (`resolveHookPermissionDecision` in `toolHooks.ts` enforces that hooks never widen permission). Power within the seams, none outside them.

---

## Failure modes

- **Hook used to bypass permissions.** A `PreToolUse` hook returns `allow` for a tool the user denied. Mitigation: `resolveHookPermissionDecision` (`toolHooks.ts`) still runs `checkRuleBasedPermissions`, so a hook `allow` cannot defeat a `deny`/`ask` rule (section 3).
- **Stop hook never lets the agent stop.** A `Stop` hook that always returns a `blockingError` makes the model self-correct, which retriggers the hook forever. Mitigation: the `stopHookActive` flag (`query/stopHooks.ts`) carries forward so it does not fire twice.
- **Hidden hook swapped mid-session.** A process edits `settings.json` after launch to inject a callback. Mitigation: `captureHooksConfigSnapshot` (`setup.ts`) freezes the active hook set once at startup.
- **Slow or hung hook stalls the loop.** A hook shells out to a slow command and the agent waits. Mitigation: `HookCallback.timeout` (`types/hooks.ts`) bounds each hook, which can also run `async`.
- **PostToolUse silently halts work.** A `PostToolUse` hook returning `preventContinuation: true` looks like the agent quitting early. Mitigation: it stops the loop gracefully via a `hook_stopped_continuation` attachment (`toolHooks.ts`), distinct from a crash (section 1).

---

## Runnable

[`src/`](src/) carries 03 forward and adds:

- [`hooks.py`](src/hooks.py): the `Hooks` object · `fire_pre` (block or rewrite the call) and `fire_post` (observe).
- [`loop.py`](src/loop.py): `_dispatch` fires PreToolUse before the gate and PostToolUse after a run.
- [`test.py`](src/test.py): a PreToolUse hook blocks `rm -rf` even under `bypassPermissions`.

```bash
python sections/04-hooks/src/test.py         # offline checks, no key
uv run python sections/04-hooks/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `types/hooks.ts`, `entrypoints/sdk/coreTypes.ts`, `services/tools/toolHooks.ts`, `query/stopHooks.ts`, `services/tools/toolExecution.ts`, `setup.ts`.
- learn-claude-code · s04_hooks: section framing.
