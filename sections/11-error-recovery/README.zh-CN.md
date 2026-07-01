# 11 · Error recovery

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 先分类失败，再重试、调整，或停止。

一次 agent 执行可能横跨很多次模型调用。任何一次调用都可能因为网络问题、过载、rate limit、输出上限或 context 溢出而失败。

循环对不同的失败需要不同的响应：

1. 对暂时性错误重试。
2. 当问题出在 prompt 或输出上限时，调整后再重试。
3. 当错误无法恢复时，停止。

没有恢复机制，一次暂时的 API 失败就能终结一项长时间的任务。

---

## 机制

把模型调用包在一个重试辅助函数里。这个辅助函数先分类失败，再采取一个有界限的行动。

- 暂时性的状态码会退避后重试。
- prompt 溢出会执行一次压缩 callback，然后重试。
- 反复的过载可以触发 fallback model。
- 未知或不可重试的错误会被抛出。

### New: classification, backoff, and the retry helper

```python
RETRY_STATUS = {408, 409, 429}                         # src/recovery.py; these plus any 5xx

def should_retry(status) -> bool:
    return status in RETRY_STATUS or (status is not None and 500 <= status < 600)

def retry_delay(attempt, retry_after=None) -> float:   # exponential backoff + jitter
    if retry_after is not None:
        return float(retry_after)
    base = min(BASE_DELAY * 2 ** (attempt - 1), MAX_DELAY)
    return base + base * 0.25 * random()
```

溢出会在一般状态处理之前先检查。如果压缩能缩小 prompt，`prompt_too_long` 错误就是可恢复的。

```python
def _status(e):
    return getattr(e, "status_code", None)

def _is_overflow(e) -> bool:
    return getattr(e, "overflow", False) or "prompt is too long" in str(e).lower()
```

`with_retry` 持有每次尝试的状态：

```python
def with_retry(call, on_overflow=None, fallback_model=None,
               max_retries=DEFAULT_MAX_RETRIES, sleep=time.sleep):
    consecutive_529 = 0
    overflowed = False
    for attempt in range(1, max_retries + 2):
        try:
            return call()
        except Exception as e:
            if _is_overflow(e):
                if on_overflow is None or overflowed:
                    raise
                overflowed = True
                on_overflow()
                continue
            status = _status(e)
            if status is None:
                raise
            if status == 529:
                consecutive_529 += 1
                if fallback_model and consecutive_529 >= MAX_529_RETRIES:
                    raise FallbackTriggered(fallback_model)
            if attempt > max_retries or not should_retry(status):
                raise
            sleep(retry_delay(attempt, getattr(e, "retry_after", None)))
```

### How it integrates

循环把它的模型调用包起来：

```python
response = recovery.with_retry(
    lambda: model(messages, registry, system),
    on_overflow=lambda: _reactive_trim(messages),
    fallback_model=fallback_model)
```

- Recovery 只包住模型调用。
- `_reactive_trim` 就地修改 `messages[]`，供一次溢出重试使用。
- 当 recovery 放弃时，错误会被浮现出来，而不是被藏起来。

---

## 各系统做法

Recovery 包住模型调用。循环主体维持不变。

| System | Retry | Token handling | Model fallback |
| --- | --- | --- | --- |
| **Claude Code** | 由状态决定、带退避的重试。 | 提高输出 token、续写，或压缩。 | 反复过载后改用 fallback。 |

### Claude Code

- `withRetry` 会重试 429、408、409 和 5xx 错误。
- `retry-after` 优先于计算出来的退避。
- 对后台来源的 529 重试次数有限制。
- 输出被截断时，可以用更高的输出上限重试。
- 续写 prompt 能救回一些 `max_tokens` 的停止。
- Reactive compaction 处理 `prompt_too_long`。
- 反复的 529 可能抛出 `FallbackTriggeredError`。

> **取舍：** 针对性的恢复路径救回的执行比一概重试更多。它们也多了更多要维护的分支与界限。

---

## 失效模式

- **Retry storm。** 许多 client 同时对过载重试会让负载更糟。限制重试次数并尊重 `retry-after`。
- **无限恢复。** 提高上限、续写和压缩都可能无限循环。为每条路径设界限。
- **溢出无法缩小。** 如果一次 reactive compaction 失败，就停止，而不是永无止境地压缩。
- **错误消失。** 一个被吞掉的错误会让 transcript 少了结果。在恢复用尽之后，把失败浮现出来。
- **Stop hook 重播 API 错误。** 对 API 错误消息略过 stop hook。

---

## 可执行程序

[`src/`](src/) 承接 10 并加入：

- [`recovery.py`](src/recovery.py)：重试分类、退避、溢出处理，以及 fallback 触发。
- [`loop.py`](src/loop.py)：把它的模型调用包在 `with_retry` 里。
- [`test.py`](src/test.py)：用一个假的不稳定调用驱动每一条路径。
- [`demo.py`](src/demo.py)：在一次 live 执行中注入一次模拟过载。

```bash
python sections/11-error-recovery/src/test.py         # offline checks, no key
uv run python sections/11-error-recovery/src/demo.py  # live demo, needs a key
```

---

## 来源

- Claude Code 源码：`services/api/withRetry.ts`、`query.ts`、`services/api/claude.ts`、`services/api/errors.ts`、`query/tokenBudget.ts`、`utils/context.ts`。
- learn-claude-code · s11_error_recovery：章节框架。
