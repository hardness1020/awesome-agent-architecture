# 6 · Subagents

**English** · [繁體中文](README.zh-TW.md)

> Run a focused child loop and return only its result.

A subagent is the agent loop run inside a tool call. The parent gives the child a prompt. The child gets a fresh `messages[]`, runs to completion, and returns its final answer.

This keeps side investigations out of the parent context. The parent does not need every file read or command result from the child. It usually needs the conclusion.

Without subagents, every investigation stays in the main transcript. Long runs become noisy, expensive, and harder for the model to follow.

---

## Mechanism

An `Agent` tool starts a child agent. The child has its own session and message list. It runs the same loop as the parent.

Only the child's final text comes back. Its transcript is discarded. File writes and shell side effects still happen in the working directory.

### New: the Agent tool

```python
def agent_tool(model, child_registry, parent_session):     # src/subagents.py
    def spawn(a):
        child = Session(mode=parent_session.mode,          # fresh context, inherited authority
                        allow_rules=set(parent_session.allow_rules))
        messages = [{"role": "user", "content": a["description"]}]   # the child's own conversation
        return run_turn(messages, model, child_registry, child)      # the loop, run again
    return Tool("Agent", spawn, is_read_only=True)
```

- `agent_tool` returns a normal tool.
- Its handler calls `run_turn()` with a new `Session`.
- The child's `messages[]` starts with only the child prompt.
- The child returns the text that `run_turn()` returns.

### How it integrates

The loop does not change. A subagent is just another tool handler that calls the loop.

Three properties matter:

- **Fresh context.** The child does not inherit the parent's transcript. The parent does not inherit the child's trace.
- **Inherited authority.** The child copies the parent's permission mode and allow rules. Context isolation is not permission isolation.
- **Recursion limit.** The demo omits `Agent` from the child registry, so a child cannot spawn another child.

---

## Per system

How each agent isolates a subproblem and returns the result.

| System | Spawn primitive | Context isolation | Result return | Resume |
| --- | --- | --- | --- | --- |
| **Claude Code** | `Agent` tool. | Fresh child messages. | Last child message text. | Most agents can resume. |

### Claude Code

- The tool lives in `tools/AgentTool/AgentTool.tsx`.
- The legacy wire name is `Task`.
- `subagent_type` selects a built-in persona.
- Built-ins include general-purpose, explore, plan, status-line setup, guide, and verification agents.
- The child loop runs in `runAgent.ts` with fresh `initialMessages`.
- `extractTextContent` returns the last message to the parent.
- `isInForkChild` prevents recursive fork spawning.
- Background subagents become `LocalAgentTask`s.
- Most agents can continue through `SendMessage` and `resumeAgent.ts`.

> **Trade-off:** A child context keeps the parent focused.
> The parent also loses the details of how the child reached its answer.
> If the summary is thin, the parent must ask again or read files the child wrote.

---

## Failure modes

- **Lossy summary.** The child may compress too much. Ask it to write important findings to disk.
- **Runaway recursion.** Children spawning children can grow without bound. Omit the `Agent` tool from child registries or enforce a depth limit.
- **No child stop.** The child has the same halt risks as the parent. Give each child its own turn or token limit.
- **Assumed permission isolation.** A child still needs the normal permission gate. Do not skip it because the context is separate.
- **Orphaned async child.** A background child can finish after the parent moves on. Track it with a task record.

---

## Runnable

[`src/`](src/) carries 05 forward and adds:

- [`subagents.py`](src/subagents.py): the `Agent` tool.
- [`loop.py`](src/loop.py): unchanged from section 5.
- [`demo.py`](src/demo.py): the parent delegates a count to a child.
- [`test.py`](src/test.py): checks fresh context, inherited authority, and recursion fencing.

```bash
python sections/06-subagents/src/test.py         # offline checks, no key
uv run python sections/06-subagents/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `tools/AgentTool/AgentTool.tsx`, `runAgent.ts`, `resumeAgent.ts`, `forkSubagent.ts`, `builtInAgents.ts`, `tasks/LocalAgentTask/`.
- learn-claude-code · s06_subagent: section framing.
