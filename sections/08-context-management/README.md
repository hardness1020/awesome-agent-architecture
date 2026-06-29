# 8 · Context management

> Context always fills up. Have a way to make room.

`messages[]` only grows (section 1). An agent that does real work reads dozens of files and runs dozens of commands in one session, and each result is appended and never removed, so the prompt grows monotonically toward a finite context window. Context management is the set of strategies that keep a long session under that window: drop stale turns, stub old tool results, persist huge outputs to disk, and as a last resort summarize the whole history into one message. When the window fills:

1. The API rejects the request outright (`prompt_too_long`).
2. Even before that, a bloated prompt is slow, expensive, and dilutes the model's attention with stale content.

Leave context management out and the agent simply dies partway through any long task. It can reason and act, but only until the window fills, then every subsequent call fails.

---

## Mechanism

Run cheap, lossless reducers first; reach for expensive, lossy summarization last. Claude Code orders four passes before each model call, then keeps a reactive fallback for when the API still returns `prompt_too_long`.

```text
budget   -> persist huge tool results to disk, leave a preview     (0 API, lossless)
snip     -> drop stale middle turns, keep head + recent tail       (0 API)
micro    -> replace old tool-result bodies with a stub placeholder (0 API)
collapse -> optional independent context system, if enabled        (0 API)
auto     -> LLM summarizes the whole history into one message       (1 API, lossy)
--- on prompt_too_long despite the above ---
reactive -> truncate the head and re-summarize, with a retry cap   (1 API, lossy)
```

Cheap passes run every turn and are near-lossless (persisted output and dropped turns are recoverable). Summarization runs only when a token threshold is crossed, because it costs a model call and discards detail. The order is load-bearing: `budget` runs before `micro` so a large tool result is written to disk before `micro` would overwrite its body with a stub.

### New: the reduction passes

```python
def manage(messages, summarizer=None):                 # src/context.py, run every turn
    _budget(messages)                                  # persist huge results   (lossless)
    _micro(messages, KEEP_RECENT)                      # stub old result bodies (cheap)
    if summarizer and estimate_tokens(messages) > TOKEN_LIMIT:
        return _auto(messages, KEEP_RECENT, summarizer)  # summarize history (lossy, last resort)
    return messages
```

- `manage` ([`src/context.py`](src/context.py)) runs the cheap passes unconditionally, then summarizes only when a token estimate crosses the limit.
- `_budget` swaps an oversized tool result for a short preview plus a `<persisted-output>` marker; `_micro` stubs the bodies of old tool results to `<elided>`; `_auto` keeps the first turn and the recent tail and collapses the middle into one summary message.

### How it integrates

One line at the top of the loop, before the model call:

```python
for _ in range(max_steps):                             # src/loop.py
    messages = context.manage(messages, summarizer=summarizer)   # 8 · keep context under the window
    response = model(messages, registry)
    ...
```

- This is the one section so far that changes [`src/loop.py`](src/loop.py): every other capability bolted on as a tool, but compaction has to run before each model call, so it lives in the loop itself.
- The passes mutate or rebuild `messages[]` and the loop reassigns, so section 1's append-and-loop invariant holds. `summarizer` defaults to `None`, so the cheap passes always run and the lossy summary is opt-in.

In Claude Code the per-turn sequence lives in `query.ts`: `applyToolResultBudget` (line 379), `snipCompactIfNeeded` (403), `microcompact` (414), `contextCollapse` (440), `autoCompact` (454). The trigger is a precise token count, not a message count: auto compaction fires when usage exceeds `getEffectiveContextWindowSize(model) - AUTOCOMPACT_BUFFER_TOKENS` (context window minus 20K reserved for the summary output, minus a 13K buffer).

---

## Per system

How each agent decides to make room and what it sacrifices.

| System                | Trigger                                                                                                  | Strategy                                                                                                                                                      | Token budget                                                                                                                                                                    |
| --------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Claude Code** | token count over`getAutoCompactThreshold(model)` (`autoCompact.ts`); reactive on `prompt_too_long` | four cheap passes then LLM summary:`applyToolResultBudget` -> snip -> `microcompactMessages` -> contextCollapse -> `autoCompactIfNeeded` (`query.ts`) | window minus 20K (`MAX_OUTPUT_TOKENS_FOR_SUMMARY`) minus 13K (`AUTOCOMPACT_BUFFER_TOKENS`); per-message tool-result cap 200K chars (`MAX_TOOL_RESULTS_PER_MESSAGE_CHARS`) |
| *(more soon)*       |                                                                                                          |                                                                                                                                                               |                                                                                                                                                                                 |

### Claude Code

Layered cheap reducers make LLM summarization rare.

- **Persist.** `applyToolResultBudget` (`utils/toolResultStorage.ts`) writes any tool result over 200K chars (`MAX_TOOL_RESULTS_PER_MESSAGE_CHARS`, `constants/toolLimits.ts`) to a `tool-results` dir, leaving a `<persisted-output>` tag plus a 2000-byte preview (`PREVIEW_SIZE_BYTES`).
- **Stub.** `microcompactMessages` (`microCompact.ts`) clears the bodies of old clearable tool results (shell, `Read`, `Grep`, web fetch) to a stub, triggered by elapsed time (`gapThresholdMinutes` 60 cache-expiry rule, `timeBasedMCConfig.ts`) or a count threshold.
- **Summarize.** Only when the precise token count still exceeds the threshold does `autoCompactIfNeeded` call the model, and even that first tries the cheaper `trySessionMemoryCompaction` (section 9).
- **Restore.** After summarizing, it restores the most recent files within a budget (`POST_COMPACT_MAX_FILES_TO_RESTORE` 5, `POST_COMPACT_MAX_TOKENS_PER_FILE` 5K, `POST_COMPACT_TOKEN_BUDGET` 50K, `compact.ts`).

> **Trade-off:** the layered pipeline buys long sessions that almost never blow the window and keeps most reductions lossless and cheap. It costs real complexity (five interacting passes, threshold math, a circuit breaker, post-compact file restore) and the chance a summary drops a detail the model later needs, forcing a re-read.

---

## Failure modes

- **Summary loses something needed.** LLM summary is lossy: a constraint or finding from 40 turns ago can vanish. Mitigation: persist the full transcript, restore recent files post-compact (`compact.ts`), and re-read on a `<persisted-output>` stub.
- **Compaction fails repeatedly.** When context is irrecoverably over the limit, every summary attempt also overflows and hammers the API. Mitigation: circuit breaker `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES` (3, `autoCompact.ts`) stops retrying for the session.
- **Context outruns proactive compaction.** One turn dumps enough output that the next call gets `prompt_too_long` before the threshold check helps. Mitigation: reactive `truncateHeadForPTLRetry` (`compact.ts`) truncates the head and re-summarizes, capped by `MAX_COMPACT_STREAMING_RETRIES` (2) (section 11).
- **Wrong pass order corrupts content.** `micro` before `budget` would stub a large tool result before persisting it, losing it permanently. Mitigation: fixed order in `query.ts` (budget 379, micro 414).
- **Broken tool-use / tool-result pair.** Dropping or stubbing messages can orphan a `tool_result` from its `tool_use`, desyncing the conversation. Mitigation: boundary checks in the snip and reactive paths never split the pair (section 1).

---

## Runnable

[`src/`](src/) carries 07 forward and adds:

- [`context.py`](src/context.py): the reduction passes `budget`, `micro`, `auto`, run via `manage`.
- [`loop.py`](src/loop.py): calls `context.manage()` at the top of every turn (the first loop change since section 5).
- [`test.py`](src/test.py): exercises each pass in isolation (persist an oversized result, stub old bodies, summarize when still over the limit).
- [`demo.py`](src/demo.py): drives the loop with `manage` wired in.

```bash
python sections/08-context-management/src/test.py         # offline checks, no key
uv run python sections/08-context-management/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `services/compact/autoCompact.ts`, `microCompact.ts`, `timeBasedMCConfig.ts`, `compact.ts`, `prompt.ts` (`<analysis>`/`<summary>` summary blocks), `utils/toolResultStorage.ts`, `query.ts` (per-turn ordering: budget 379, snip 403, micro 414, collapse 440, auto 454), `query/tokenBudget.ts` (`checkTokenBudget`).
- learn-claude-code · s08_context_compact: section framing.

Inferred, not fully in this clone:

- `snipCompact.ts`: gated by `HISTORY_SNIP` in `query.ts`, so only its `snipCompactIfNeeded(messages)` call site is visible, not the body.
- `reactiveCompact.ts`: no such file; the reactive path lives in `compact.ts` (that name appears only in a comment).
