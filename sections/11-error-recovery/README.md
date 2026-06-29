# 11 · Error recovery

> Errors aren't the end, they're the start of a retry.

A long agent run spans dozens of model calls, and the loop (section 1) is a `while` around each one. That call lives over a network, against a shared service, with a hard token budget on both ends, and any call can fail: the API is overloaded, the output gets truncated, the prompt no longer fits. In production, failure is the common case, not the exception:

1. **Transient capacity.** 429 rate limit, 529 overload, dropped connection.
2. **Truncated output.** The model hits `max_tokens` mid-answer.
3. **Context overflow.** The prompt is too long even after compaction (section 8).

Leave this out and a single 529 ends a task that was 90% done. The loop must distinguish "retry verbatim", "retry with an adjustment", and "give up", and apply the right one per error class.

---

## Mechanism

Wrap the model call in a retry generator. Classify the failure, then take the matching path: back off and retry, adjust a parameter and retry, or raise. State (consecutive 529s, escalation flag, recovery count) persists across attempts so each path fires a bounded number of times.

### New: classification, backoff, and the retry generator

Two small functions classify a failure and price the wait. `should_retry` gates by status; `retry_delay` is exponential backoff with jitter, but a server `retry-after` header always wins:

```python
RETRY_STATUS = {408, 409, 429}                         # src/recovery.py; these plus any 5xx

def should_retry(status) -> bool:
    return status in RETRY_STATUS or (status is not None and 500 <= status < 600)

def retry_delay(attempt, retry_after=None) -> float:   # exponential backoff + up to 25% jitter
    if retry_after is not None:
        return float(retry_after)                      # the server told us when; obey it
    base = min(BASE_DELAY * 2 ** (attempt - 1), MAX_DELAY)
    return base + base * 0.25 * random()
```

The classification itself is duck-typed off the exception, so the same code handles the anthropic SDK's errors and the test's fakes. Overflow is checked first, before status, because a `prompt_too_long` is a 400 we want to compact rather than treat as fatal:

```python
def _status(e):                                        # the HTTP status of an API error, or None
    return getattr(e, "status_code", None)

def _is_overflow(e) -> bool:                           # context overflow, recognized before status
    return getattr(e, "overflow", False) or "prompt is too long" in str(e).lower()
```

`with_retry` is the generator that ties them together. Each `except` branch is one error class, and the per-attempt state (`consecutive_529`, `overflowed`) is what bounds each path:

```python
def with_retry(call, on_overflow=None, fallback_model=None,
               max_retries=DEFAULT_MAX_RETRIES, sleep=time.sleep):
    consecutive_529 = 0
    overflowed = False
    for attempt in range(1, max_retries + 2):
        try:
            return call()
        except Exception as e:
            if _is_overflow(e):                        # prompt too long
                if on_overflow is None or overflowed:
                    raise                              # compacted once already, nothing left to shrink
                overflowed = True
                on_overflow()                          # compact (section 8), then retry
                continue
            status = _status(e)
            if status is None:
                raise                                  # not a recognized API error -> fatal
            if status == 529:
                consecutive_529 += 1
                if fallback_model and consecutive_529 >= MAX_529_RETRIES:
                    raise FallbackTriggered(fallback_model)
            if attempt > max_retries or not should_retry(status):
                raise                                  # exhausted or non-retryable -> surface it
            sleep(retry_delay(attempt, getattr(e, "retry_after", None)))
```

- **Transient** (429 / 408 / 409 / 5xx): `should_retry` says yes, so back off `retry_delay` and retry, up to `DEFAULT_MAX_RETRIES`.
- **Overflow** (`prompt too long`): run `on_overflow` once to compact (section 8), then retry; if it still overflows, surface it, because compacting again will not help.
- **529 storm**: after `MAX_529_RETRIES` consecutive overloads, raise `FallbackTriggered` so the caller can switch models.
- **Fatal** (4xx, or any unrecognized error): raise at once. Truncation (`stop_reason == "max_tokens"`) is a separate loop-level branch, not shown here.

### How it integrates

The loop wraps its one model call; the body is otherwise the section-10 loop:

```python
response = recovery.with_retry(                        # src/loop.py · 11 · retry / adapt / fall back
    lambda: model(messages, registry, system),
    on_overflow=lambda: _reactive_trim(messages),      # in-place last-resort compaction
    fallback_model=fallback_model)
```

- `on_overflow` is `_reactive_trim`, which drops the middle of `messages[]` in place (keeping the head plus recent tail, never orphaning a `tool_result`), so the one retry sends a shorter prompt.
- Recovery only wraps the call. When it finally raises, the error returns to `messages[]` as a normal result and the loop reasons over it (section 1).

---

## Per system

Recovery wraps the model call; the loop body (section 1) is unchanged.

| System | Retry | Token escalation | Model fallback |
|---|---|---|---|
| **Claude Code** | `withRetry`, status-gated, up to `DEFAULT_MAX_RETRIES` (10) | escalate to `ESCALATED_MAX_TOKENS`, then inject a continuation prompt | `FallbackTriggeredError` after 3 consecutive 529s |
| *(more soon)* | | | |

### Claude Code

- **Retry.** `withRetry` (`services/api/withRetry.ts`) retries up to `DEFAULT_MAX_RETRIES` (10); `getRetryDelay` = `min(500·2^(n-1), 32000)` + up to 25% jitter, `retry-after` header wins; `shouldRetry` gates by status (429/408/409/5xx).
- **Token escalation.** `max_output_tokens_escalate` retries the same request at `ESCALATED_MAX_TOKENS` (64K, `utils/context.ts`), then `max_output_tokens_recovery` injects a continuation prompt up to `MAX_OUTPUT_TOKENS_RECOVERY_LIMIT` times.
- **Model fallback.** After `MAX_529_RETRIES` (3) consecutive 529s, `withRetry` throws `FallbackTriggeredError(model, fallbackModel)`; `services/api/claude.ts` propagates it to `query.ts`, which retries on the `fallbackModel`.

> **Trade-off:** classifying errors into many recovery paths (Claude Code evaluates a dozen-plus transition reasons after each call: `max_output_tokens_escalate`, `reactive_compact_retry`, `token_budget_continuation`, and more) recovers far more runs than a blanket "retry N times", but every path is a guarded code branch with its own bound, and a misclassified error can either spin or surface too early. The alternative, retry-or-die, is trivial to audit but throws away most recoverable failures.

---

## Failure modes

- **Retry storm during a capacity cascade.** Every client retrying a 529 amplifies load. Mitigation: retry 529 only for foreground sources (`FOREGROUND_529_RETRY_SOURCES`); background calls (titles, classifiers) bail at once via `CannotRetryError`.
- **Infinite recovery.** Escalation, continuation, and reactive compaction each loop back to the model. Mitigation: bound each (escalation once via `maxOutputTokensOverride`, continuation by `MAX_OUTPUT_TOKENS_RECOVERY_LIMIT`, reactive compact by `hasAttemptedReactiveCompact`) and stop on diminishing returns (`tokenBudget.ts`: 3 continuations gaining under `DIMINISHING_THRESHOLD` of 500 tokens).
- **Overflow with nowhere to shrink.** A prompt still `prompt_too_long` after one reactive compaction (section 8) cannot shrink further. Mitigation: exit instead of retrying, since compacting again loops forever.
- **Error never reaches the model.** A swallowed failure leaves the loop reasoning over a hole (section 1). Mitigation: surface the withheld error as a message once recovery is exhausted; otherwise the loop self-corrects silently.
- **Death spiral via stop hooks.** A stop hook (section 4) evaluating an API-error message can block, retry, and re-error. Mitigation: skip stop hooks when the last message `isApiErrorMessage`, returning `completed`.

---

## Runnable

[`src/`](src/) carries 10 forward and adds:

- [`recovery.py`](src/recovery.py): `with_retry` classifies each failure into back-off-and-retry, compact-then-retry (overflow), `FallbackTriggered` (529 storm), or fatal.
- [`loop.py`](src/loop.py): wraps its model call in `with_retry`, with an in-place reactive trim as the overflow handler.
- [`test.py`](src/test.py): drives each path with a fake flaky call.
- [`demo.py`](src/demo.py): injects one simulated overload so a live run visibly recovers.

```bash
python sections/11-error-recovery/src/test.py         # offline checks, no key
uv run python sections/11-error-recovery/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `services/api/withRetry.ts`, `query.ts`, `services/api/claude.ts`, `services/api/errors.ts`, `query/tokenBudget.ts`, `utils/context.ts`.
- learn-claude-code · s11_error_recovery: section framing.
