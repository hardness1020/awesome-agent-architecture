# 11 · Error recovery

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 先分类失败，再重试、调整，或停止。

一次 agent 执行可能横跨很多次模型调用。任何一次调用都可能因为网络问题、过载、rate limit、输出上限或 context overflow 而失败。

loop 对不同的失败需要不同的响应：

1. 对暂时性错误重试。
2. 当问题出在 prompt 或输出上限时，调整后再重试。
3. 当错误无法恢复时，停止。

没有恢复机制，一次暂时的 API 失败就能终结一项长时间的任务。

---

## 机制

![机制图](assets/11-error-recovery.png)

把模型调用包在一个重试辅助函数里。这个辅助函数先分类失败，再采取一个有界限的行动。

- 暂时性的状态码会退避后重试。
- prompt overflow 会执行一次压缩 callback，然后重试。
- 反复的过载可以触发 fallback model。
- 未知或不可重试的错误会被抛出。

### New: 分类、backoff 与 retry helper

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

overflow 会在一般状态处理之前先检查。如果压缩能缩小 prompt，`prompt_too_long` 错误就是可恢复的。

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

### 如何整合

loop 把它的模型调用包起来：

```python
response = recovery.with_retry(
    lambda: model(messages, registry, system),
    on_overflow=lambda: _reactive_trim(messages),
    fallback_model=fallback_model)
```

- Recovery 只包住模型调用。
- `_reactive_trim` 就地修改 `messages[]`，供一次 overflow 重试使用。
- 当 recovery 放弃时，错误会被浮现出来，而不是被藏起来。

---

## 各系统做法

Recovery 包住模型调用。loop 主体维持不变。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 针对性的恢复路径救回的 run 比一概重试更多。 | 只有三条路径要维护。就算 crash，磁盘上也留有完整轨迹。 |
| **Cons** | 要维护的分支与界限更多。 | 救回的 run 较少。context overflow 直接中止，连续三次格式错误也会结束 run。 |
| **Why** | 一次暂时的 API 失败不该终结长任务。 | 只留三条路：暂时性错误就重试、格式错误还给模型、其余带着具名状态退出。 |
| **How: retry** | 带退避重试 429、408、409 和 5xx，`retry-after` 优先。 | tenacity 退避 4 到 60 秒，最多 10 次。救不回的错误直接跳过。 |
| **How: token handling** | 提高输出 token、在 `max_tokens` 停止后续写，或在 `prompt_too_long` 时压缩。 | 没有，context overflow 直接中止 run。 |
| **How: model fallback** | 反复过载（529）后改用 fallback。后台来源的 529 重试次数有限制。 | 没有。 |

---

## 哪里会出错

- **Retry storm：**许多 client 同时对过载重试会让负载更糟。限制重试次数并尊重 `retry-after`。
- **无限恢复：**提高上限、续写和压缩都可能无限 loop。为每条路径设界限。
- **overflow 无法缩小：**如果一次 reactive compaction 失败，就停止，而不是永无止境地压缩。
- **错误消失：**一个被吞掉的错误会让 transcript 少了结果。在恢复用尽之后，把失败浮现出来。
- **Stop hook 重播 API 错误：**对 API 错误消息略过 stop hook。

---

## 可执行程序

[`src/`](src/) 承接 10 并加入：

- [`recovery.py`](src/recovery.py)：重试分类、退避、overflow 处理，以及 fallback 触发。
- [`loop.py`](src/loop.py)：把它的模型调用包在 `with_retry` 里。
- [`test.py`](src/test.py)：用一个假的不稳定调用驱动每一条路径。
- [`demo.py`](src/demo.py)：在一次 live 执行中注入一次模拟过载。

```bash
python sections/11-error-recovery/src/test.py         # offline checks, no key
uv run python sections/11-error-recovery/src/demo.py  # live demo, needs a key
```

---

## 来源

- [Claude Code 源码](https://github.com/yasasbanukaofficial/claude-code)：`services/api/withRetry.ts`、`query.ts`、`services/api/claude.ts`、`services/api/errors.ts`、`query/tokenBudget.ts`、`utils/context.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`models/utils/retry.py`、`models/litellm_model.py`、`agents/default.py` 的 `run()` 与 `max_consecutive_format_errors`。
- [learn-claude-code · s11_error_recovery](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
