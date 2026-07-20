# 8 · Context management

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> Keep long sessions under the context limit.

`messages[]` grows during a run. Each tool result, assistant reply, and user turn adds more text. A long session will eventually reach the model's context limit.

Context management keeps the session usable. It removes, stubs, persists, or summarizes old content before the next model call.

When context fills:

1. The API can reject the request.
2. Calls become slower and more expensive.
3. Old, less useful content competes with current task information.

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

This is a real loop change. Earlier sections added tools or dispatch behavior. Context must run before the model call, so it belongs in the loop.

The loop still keeps the same invariant: it calls the model with a valid `messages[]`, then appends the response and any tool results.

---

## Per system

How each agent decides to make room and what it removes.

| System | Trigger | Strategy | Budget rule |
| --- | --- | --- | --- |
| **Claude Code** | Token threshold plus overflow fallback. | Cheap reducers first, then LLM summary. | Reserve output and safety buffers. |

### Claude Code

- `query.ts` runs the passes before model calls.
- `applyToolResultBudget` persists tool results over the per-message character cap.
- Persisted results leave a preview and a path-like marker.
- `microcompactMessages` clears old tool-result bodies to a stub.
- `autoCompactIfNeeded` calls the model only after token count still exceeds the threshold.
- After compaction, recent files can be restored within a token budget.
- Reactive compaction handles a `prompt_too_long` response after proactive passes failed.

> **Trade-off:** Layered reducers make long sessions possible and keep many reductions cheap.
> They add ordering rules and summary risk.
> A summary can omit detail the model later needs.

---

## Failure modes

- **Summary loses needed detail.** Persist full outputs and re-read files when needed.
- **Compaction fails repeatedly.** Use a retry cap or circuit breaker.
- **One huge turn overflows anyway.** React to `prompt_too_long` with a bounded last-resort trim.
- **Wrong pass order loses data.** Persist large results before stubbing old results.
- **Broken tool pairs.** Do not split a `tool_use` from its matching `tool_result`.

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

- Claude Code source: `services/compact/autoCompact.ts`, `microCompact.ts`, `timeBasedMCConfig.ts`, `compact.ts`, `utils/toolResultStorage.ts`, `query.ts`, `query/tokenBudget.ts`.
- learn-claude-code · s08_context_compact: section framing.

Inferred, not fully in this clone:

- `snipCompact.ts`: only the `snipCompactIfNeeded(messages)` call site is visible.
- `reactiveCompact.ts`: the reactive path appears to live in `compact.ts`.
