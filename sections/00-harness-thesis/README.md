# 0 · Harness thesis

> The model decides what to do. The harness gives it tools, state, and limits.

The model owns reasoning, tool choice, and when to stop. The harness is the code around the model: the loop, tools, memory, permissions, and interfaces.

A model call alone is one response to one input. It can decide to act, but it cannot act by itself. It has no durable state, no tool runner, no file access, and no permission gate.

The harness must:

1. Give actions a place to run.
2. Give the model useful observations.
3. Gate side effects before they reach the world.
4. Persist state so later calls build on earlier calls.

Without a harness, the model can only answer. It cannot run tools, observe results, or remember work across calls.

---

## Mechanism

This section is about decomposition. A small model call sits at the center. The harness supplies its inputs and handles its outputs.

The model owns judgment. The harness owns the environment.

```mermaid
flowchart TB
    K[knowledge: memory · skills · prompt] --> M
    O[observation: tool results · context] --> M
    M{{model}} -->|tool_use| A[actions: tool runtime · dispatch]
    A --> P[permissions: gate side effects]
    P --> A
    A --> O
    M -->|end_turn| D([reply])
```

The loop in section 1 is the core control flow. Other sections add inputs, checks, or state around it:

- Section 2 adds the tool runtime and dispatch.
- Section 3 adds permissions and sandboxing.
- Section 4 adds hooks that intercept lifecycle events.
- Sections 8 and 9 add context management and memory.
- Section 10 assembles the system prompt each turn.
- Later sections add tasks, background work, scheduling, and isolation.

These parts do not replace the loop. They feed it, gate it, or persist state for it.

---

## Per system

What the model decides versus what the surrounding code builds.

| System | What the model owns | What the harness owns | Size signal |
| --- | --- | --- | --- |
| **Claude Code** | Judgment, tool choice, and stop decisions. | Loop, tools, permissions, hooks, knowledge, tasks, and coordination. | Most code sits outside the model call. |

### Claude Code

- The model is reached through `QueryEngine.ts`.
- `tools/` defines actions.
- `hooks/` defines lifecycle interception.
- `skills/` and `memdir/` define knowledge loading and recall.
- `tasks/` and `coordinator/` define longer-running and multi-agent work.
- `Tool.ts` gives tools a shared contract: `name`, `inputSchema`, `isEnabled()`, `checkPermissions()`, and `prompt()`.
- The model sees tool names, schemas, and results. It does not run dispatch or permission code.

> **Trade-off:** The harness adds safety, persistence, subagents, and on-demand knowledge.
> It also becomes the main code surface. Most behavior and most bugs live there.

---

## Failure modes

- **Crediting the model for harness behavior.** Permission checks and error recovery are harness behavior. Fix the harness when they fail.
- **Hard-coding decisions the model should make.** Rigid tool order and scripted planning can fight the model. Let the model decide when judgment is required.
- **Too little harness.** A loop with no tools, permissions, or context management keeps the model at chatbot behavior. Add the missing layer.
- **Too much harness.** Every new layer adds code to maintain. Use observability and evaluation to check that the harness still works.
- **Mixed responsibilities.** Permission logic inside tool execution is harder to test and replace. Keep clear contracts such as `Tool.ts` and `PreToolUse`.

---

## Sources

- Claude Code source (`cc-src/src`): `QueryEngine.ts`, `query/`, `Tool.ts`, `tools/`, `hooks/`, `types/permissions.ts`.
- learn-claude-code · s20_comprehensive: section framing.
