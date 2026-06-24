# 1 · Agent Loop

> One loop, and almost nothing else. Everything in this repo hangs off this branch.

The model decides; the loop lets it keep deciding. Strip the branding from any agent and you find the same `while`: call the model, and if it asked for a tool, run it, feed the result back, call again.

---

## Problem

A raw model call is one-shot. You send messages, you get one response, it stops. That is a chatbot, not an agent. An agent has to act, see what happened, and decide again, possibly many times, with no human pressing enter between steps.

So something must:

1. Carry the conversation state across turns.
2. Detect when the model wants to act versus when it is done.
3. Run the requested action and feed the outcome back.
4. Re-invoke the model and repeat until it stops.

Leave this out and the model can reason but never acts. Get it wrong and the agent either halts too early (drops the task) or never halts (burns tokens in a tool-call loop).

---

## Mechanism

Three pieces: a growing `messages[]` list, a `while` loop, and a branch on the model's `stop_reason`.

```mermaid
flowchart LR
    U([User intent]) --> M["messages[]"]
    M --> L{{model call}}
    L -->|stop_reason: tool_use| T[run tools]
    T --> A[append results] --> M
    L -->|stop_reason: end_turn| D([reply to user])
```

```python
messages = [user_intent]
while True:
    reply = model(messages, tools)        # one model call
    messages.append(reply)
    if reply.stop_reason == "tool_use":   # model wants to act
        for call in reply.tool_calls:
            result = run_tool(call)        # dispatch + execute
            messages.append(result)       # feed the outcome back
        continue                          # loop: let the model see results
    if reply.stop_reason == "end_turn":   # model is done
        return reply.text                 # reply to the user
```

The loop body never changes as you add capability. Permissions (subsystem 3), subagents (6), memory (9), and hooks (4) bolt onto the four numbered steps; they are not rewrites of the `while`.

Two `stop_reason` values drive everything:

- `tool_use` the model emitted tool calls. Run them, append results, loop.
- `end_turn` the model produced a final answer. Stop.

`messages[]` is the entire memory of the run. Each appended tool result is what lets the next model call build on the last action. That append-and-loop is the agent.

This bare loop has no permission gate. Gating side effects is a separate concern layered on step 3 (see subsystem 3).

---

## Per system

How each agent owns that `while` and decides to stop.

| System | Loop driver | Stop signal | Parallel tools | Streaming |
|---|---|---|---|---|
| **Claude Code** | `QueryEngine.ts` + `query/` (async generator) | `stop_reason: end_turn` | yes | yes |
| *(more soon)* | | | | |

Claude Code runs the loop as an async generator. The `query/` module yields each step (model token, tool call, tool result) as it happens, which is what drives the live-updating terminal. Tool calls within one model turn can run in parallel, and the `Tool.ts` contract is how each tool plugs into dispatch. The loop itself stays the trivial branch above.

> **Trade-off:** a one-file bash loop (model returns a command, you run it, repeat) is trivial to read and audit, but it cannot gate side effects, run tools in parallel, or stream output. A generator-based loop like Claude Code's buys permissions, parallelism, and live output at the cost of a much larger surface. Choose by whether you need to gate what the model does.

---

## Failure modes

- **No stop condition.** A bug that never yields `end_turn`, or a tool that always provokes another tool call, loops forever. Real loops add a max-iteration or token ceiling as a backstop.
- **Context overflow mid-loop.** `messages[]` only grows, so long runs blow the context window. This is why context management (subsystem 8) exists; the loop alone has no answer.
- **Partial tool failure.** A tool throws or times out. If the error is not appended as a result, the model never learns it failed and may hang or repeat. The outcome, including failure, must always go back into `messages[]`.
- **Lost results.** Appending the model reply but forgetting the tool result (or the reverse) desyncs the conversation, and the next call reasons over a hole.

---

## Runnable

[`agent_loop.py`](agent_loop.py) is the loop above in ~60 lines with a stubbed model, so it runs with no API key. It fakes two model turns (one tool call, then a final answer) to show the branch and the append-back. Swap the stub for a real client and the loop body does not change.

```
python dimensions/01-agent-loop/agent_loop.py
```

---

## Sources

- Claude Code leaked source structure (`QueryEngine.ts`, `query/`, `Tool.ts`): [backup repo](https://github.com/yasasbanukaofficial/claude-code)
- Framing: [learn-claude-code · s01 Agent Loop](https://github.com/shareAI-lab/learn-claude-code)

Educational reconstruction from public structure and observed behavior, not an official description of any system.
