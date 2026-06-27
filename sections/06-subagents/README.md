# 6 · Subagents

> Big tasks split small, each subtask gets a clean context.

A subagent is the agent loop (section 1) run again inside a tool call. The parent spawns a child with a fresh `messages[]`, the child runs its own loop to completion, and only its final answer comes back. The exploration that produced that answer never enters the parent's context.

---

## Problem

A single loop accumulates everything. To fix one bug the agent reads 30 files and chats 60 turns; `messages[]` swells to 120 entries, most of them the trace, not the goal. That noise crowds the window, the model drifts, and it forgets the original task (this is why context management, section 8, exists).

The human move is to open a second terminal, do the side investigation there, jot the result, and return to the first terminal to keep working. An agent needs the same: a clean child process with its own message list, focused on one thing, whose intermediate steps you can throw away. Leave it out and every digression permanently pollutes the main thread.

---

## Mechanism

A `task` style tool spawns a child agent. The child gets a fresh `messages[]` seeded only with a prompt, runs its own loop to a stop, and returns just the text of its last message. The transcript is discarded; filesystem side effects (writes, edits, commands) persist in the working directory.

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

- `agent_tool` ([`src/subagents.py`](src/subagents.py)) returns an ordinary `Tool`. Its `run` calls `run_turn()` from section 1, the same loop, with a brand-new `Session` and a `messages[]` seeded only by the description.
- The child returns the text of its last message (`run_turn()` already returns exactly that), so the parent receives a conclusion, never the child's transcript.

### How it integrates

No loop change. A subagent is the section-1 loop invoked inside a tool call, so [`src/loop.py`](src/loop.py) is byte-identical to section 5. Three properties fall out of that:

- **Fresh context:** the child's `messages[]` is local to its `run_turn()` call and discarded on return, so the parent's history cannot distract the child and the child's history cannot bloat the parent.
- **Inherited authority:** the child `Session` copies the parent's `mode` and `allow_rules`, so the child's own calls still hit the section-3 gate. Isolating context does not isolate permission.
- **Recursion fenced:** `child_registry` omits the `Agent` tool, so a child cannot spawn another. (Claude Code fences the same risk with `isInForkChild`.)

---

## Per system

How a parent isolates a subproblem and gets the answer back.

| System                | Spawn primitive                                                                            | Context isolation                                       | Result return                                              | Resume?                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **Claude Code** | `Agent` tool (`AGENT_TOOL_NAME`, legacy `Task`); `subagent_type` + `description` | child loop in`runAgent.ts`, fresh `initialMessages` | `extractTextContent` of last message (`AgentTool.tsx`) | yes,`resumeAgent.ts` for addressable agents; `Explore`/`Plan` are one-shot |
| *(more soon)*       |                                                                                            |                                                         |                                                            |                                                                                  |

### Claude Code

- **Spawn primitive.** The `Agent` tool in `tools/AgentTool/AgentTool.tsx` (`AGENT_TOOL_NAME = 'Agent'`, addressable under the legacy wire name `Task`).
- **Personas.** `subagent_type` selects one; `getBuiltInAgents()` (`builtInAgents.ts`) registers `GENERAL_PURPOSE_AGENT`, `EXPLORE_AGENT`, `PLAN_AGENT`, `STATUSLINE_SETUP_AGENT`, `CLAUDE_CODE_GUIDE_AGENT`, `VERIFICATION_AGENT` (each under `built-in/`).
- **Same loop.** The child runs the parent's loop in `runAgent.ts` with a fresh `initialMessages`; the parent receives only `extractTextContent` of the last message.
- **Recursion fenced.** `isInForkChild` (`forkSubagent.ts`) rejects a fork child already carrying `FORK_BOILERPLATE_TAG`.
- **Sync or async.** `run_in_background` returns `status: 'async_launched'`, tracked as a `LocalAgentTask` (`tasks/LocalAgentTask/`).
- **Resume.** Most agents stay addressable via `SendMessage` and continue through `resumeAgent.ts`; one-shot `Explore`/`Plan` report once and skip the resume trailer.

> **Trade-off:** a fresh `messages[]` per child buys focus and a clean parent thread, but the parent loses all visibility into how the answer was reached. If the summary is wrong or thin, the parent cannot inspect the steps; it can only re-delegate. You trade debuggability and shared learning for context hygiene.

---

## Failure modes

- **Lossy summary.** The child compresses a long investigation into one message; the parent acts on a thin conclusion it cannot inspect. Mitigation: have the child write findings to disk for the parent to read, not just return prose.
- **Runaway recursion.** A child that can spawn children fans out without bound, exploding depth and cost. Mitigation: omit `Agent` from `child_registry` and fence forks with `isInForkChild` checking `FORK_BOILERPLATE_TAG` (`forkSubagent.ts`).
- **No stop in the child.** The child runs its own loop, inheriting the halting risk (section 1), so one delegation can burn the whole budget. Mitigation: a `MAX_TURNS` or token ceiling per child.
- **Assumed permission isolation.** Context isolation is not authority isolation; skipping gates "because it is just a subagent" reopens every side-effect risk. Mitigation: route the child's tool calls through the same permission pipeline (section 3).
- **Orphaned async children.** A backgrounded spawn (`run_in_background`) outlives its turn; a dropped completion notification leaves the parent waiting forever. Mitigation: track it via the `LocalAgentTask` record (sections 12, 13).

---

## Runnable

[`src/`](src/) carries 05 forward and adds:

- [`subagents.py`](src/subagents.py): the `Agent` tool, whose `run` calls `run_turn()` (section 1) with a fresh `Session` and `messages[]`.
- [`loop.py`](src/loop.py): byte-identical to section 5, because a subagent is that loop run again.
- [`demo.py`](src/demo.py): the parent delegates counting the python files to a child; only the child's conclusion returns.
- [`test.py`](src/test.py): offline checks of fresh context, inherited authority, and recursion fencing.

```bash
python sections/06-subagents/src/test.py         # offline checks, no key
uv run python sections/06-subagents/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `tools/AgentTool/AgentTool.tsx`, `runAgent.ts`, `resumeAgent.ts`, `forkSubagent.ts`, `builtInAgents.ts`, `tasks/LocalAgentTask/`.
- learn-claude-code · s06_subagent: section framing.
