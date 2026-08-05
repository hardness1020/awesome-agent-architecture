# 8 · Context management

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> Keep long sessions under the context limit.

`messages[]` grows during a run. Each tool result, assistant reply, and user turn adds more text. A long session will eventually reach the model's context limit.

Context management keeps the session usable. It removes, stubs, persists, or summarizes old content before the next model call.

When context fills:

1. The API can reject the request.
2. Calls become slower and more expensive.
3. Old, less useful content competes with current task information.

The third item has a name: context rot. Retrieval precision falls as irrelevant text piles up, well before the window is full.
The agent keeps running. It just decides worse.

Compression has a second motive beyond fit and cost. In-context learning behaves like retrieval, not like reasoning.
Attention finds a fact that is written down, but it does not reliably combine facts scattered across dozens of turns.
A short precomputed summary beats leaving the model to re-derive the same conclusion from raw logs on every call.
So a good compaction improves answer quality even when the window still has room.

Without this layer, long tasks fail once the prompt no longer fits.

---

## Mechanism

![Mechanism diagram](assets/08-context-management.png)

Use cheap reducers before summarization. Cheap reducers are local and mostly lossless. Summarization costs a model call and can lose detail.

Claude Code uses a layered order:

```text
budget   -> persist huge tool results to disk, leave a preview
snip     -> drop stale middle turns, keep head + recent tail
micro    -> replace old tool-result bodies with a stub
collapse -> optional independent context system
auto     -> LLM summarizes the whole history into one message
--- on prompt_too_long despite the above ---
reactive -> truncate the head and re-summarize, with a retry cap
```

Order matters. For example, a large tool result should be persisted before any pass replaces its body with a stub.

The replacement text itself must be stable. Freeze the stub string at first use and reuse it byte for byte, including after a session is restored from disk.
A stub that re-renders with a fresh timestamp or a new path changes the prefix and throws away the cache.

That cache cost also shapes the trigger. Any edit to the history invalidates the cached prefix from the edit point onward.
Trimming a little on every turn pays that rebuild every turn. One larger reduction at a token threshold pays it once.
This is why compaction batches instead of running continuously. It belongs between API calls, never inside one.

The Claude API offers a server-side version of the same idea. Context editing clears older tool results out of the prefix, so the harness ships no code for that pass.
It still rebuilds the cache once, so it belongs near the overflow end of the order rather than on every turn.

What a summary keeps matters as much as when it runs. Condition the summary on the current task instead of asking for a generic recap of the session.
A task-aware summary answers one question: what does the next call still need. Keep, in this order:

1. Architecture and design decisions already made.
2. Files created or changed, and what changed in them.
3. Pass and fail status of the last checks or tests.
4. Open TODOs and the current step.

Raw tool output is the first thing to drop. The budget pass already wrote the large results to disk, so the agent can re-read one when it matters.

### New: the reduction passes

```python
def manage(messages, summarizer=None):                 # src/context.py, run every turn
    _budget(messages)                                  # persist huge results   (lossless)
    _micro(messages, KEEP_RECENT)                      # stub old result bodies (cheap)
    if summarizer and estimate_tokens(messages) > TOKEN_LIMIT:
        return _auto(messages, KEEP_RECENT, summarizer)  # summarize history (lossy, last resort)
    return messages
```

- `manage` runs cheap passes each turn.
- `_budget` writes oversized tool results to disk and leaves a short preview.
- `_micro` stubs old tool-result bodies.
- `_auto` keeps the first turn and recent tail, then summarizes the middle.
- `summarizer=None` disables lossy summarization in the demo.

### How it integrates

Context management runs before each model call:

```python
for _ in range(max_steps):                             # src/loop.py
    messages = context.manage(messages, summarizer=summarizer)   # 8 · keep context under the window
    response = model(messages, registry)
    ...
```

This section changes the loop body itself. Earlier sections added tools or dispatch behavior and left the loop alone.
Context reduction must run before every model call, so it has to live in the loop.

The loop still keeps the same invariant: it calls the model with a valid `messages[]`, then appends the response and any tool results.

---

## Per system

How each agent decides to make room and what it removes.

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | Long sessions survive. Most reductions are cheap, and persisted outputs can be re-read. | Nothing to schedule or tune. Easy to audit. |
| **Cons** | Passes need ordering rules. A summary can drop detail the model later needs. | History only grows. A run that outlives its budget dies on overflow. |
| **Why** | Interactive sessions are open ended, so the window will fill. | Assumes a task ends, by submission or cost limit (section 21), before the window fills. |
| **How: trigger** | Token threshold, plus a reactive fallback on `prompt_too_long`. | Every observation, at render time. |
| **How: strategy** | Cheap reducers first (persist big results, stub old ones), LLM summary last. | Truncate long output to a head and a tail. No compaction. |
| **How: budget** | Reserve output and safety buffers. | 10k characters per observation. |

---

## Failure modes

- **Summary loses needed detail.** Persist full outputs and re-read files when needed.
- **Compaction fails repeatedly.** Use a retry cap or circuit breaker.
- **One huge turn overflows anyway.** React to `prompt_too_long` with a bounded last-resort trim.
- **Wrong pass order loses data.** Persist large results before stubbing old results.
- **Broken tool pairs.** Do not split a `tool_use` from its matching `tool_result`.
- **Stub text drifts.** A preview that re-renders with a new timestamp or path changes the prefix and drops the cache. Freeze the string at first use.
- **Trimming on every turn.** Each edit invalidates the cache after the edit point, so many small reductions cost more than one batched pass. Trigger on a threshold.
- **The model trusts the summary.** Injected state is read as fact and rarely re-checked. Leave pointers to the persisted originals so a wrong summary can be caught.

---

## Runnable

[`src/`](src/) carries 07 forward and adds:

- [`context.py`](src/context.py): `budget`, `micro`, and `auto` passes run through `manage`.
- [`loop.py`](src/loop.py): calls `context.manage()` at the top of every turn.
- [`test.py`](src/test.py): checks each pass in isolation.
- [`demo.py`](src/demo.py): drives the loop with context management wired in.

```bash
python sections/08-context-management/src/test.py         # offline checks, no key
uv run python sections/08-context-management/src/demo.py  # live demo, needs a key
```

---

## Sources

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code):
  `services/compact/autoCompact.ts`, `microCompact.ts`, `timeBasedMCConfig.ts`, `compact.ts`, `utils/toolResultStorage.ts`, `query.ts`, `query/tokenBudget.ts`.
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent): the observation template in `config/mini.yaml`, `abort_exceptions` in `models/litellm_model.py`.
- [learn-claude-code · s08_context_compact](https://github.com/shareAI-lab/learn-claude-code): section framing.
- [ai-agent-book · chapter 2](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter2.md) (《深入理解 AI Agent》, 李博杰; the Chinese original is canonical):
  context rot, in-context learning as retrieval, the compression and cache interplay, task-aware compression with retention priorities,
  API-level context editing, the frozen tool-result stub, and the finding that models read an injected summary as fact.
- [Lost in the Middle](https://arxiv.org/abs/2307.03172) (Liu et al., TACL 2024): retrieval accuracy drops for facts placed in the middle of a long context. Grounds context rot.

Inferred; not fully present in the Claude Code source repo above:

- `snipCompact.ts`: only the `snipCompactIfNeeded(messages)` call site is visible.
- `reactiveCompact.ts`: the reactive path appears to live in `compact.ts`.
