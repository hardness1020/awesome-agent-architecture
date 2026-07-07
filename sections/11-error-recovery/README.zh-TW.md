# 11 · Error recovery

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 先分類失敗，再重試、調整，或停止。

一次 agent 執行可能橫跨很多次模型呼叫。任何一次呼叫都可能因為網路問題、過載、rate limit、輸出上限或 context 溢位而失敗。

迴圈對不同的失敗需要不同的回應：

1. 對暫時性錯誤重試。
2. 當問題出在 prompt 或輸出上限時，調整後再重試。
3. 當錯誤無法復原時，停止。

沒有復原機制，一次暫時的 API 失敗就能終結一項長時間的任務。

---

## 機制

把模型呼叫包在一個重試輔助函式裡。這個輔助函式先分類失敗，再採取一個有界限的行動。

- 暫時性的狀態碼會退避後重試。
- prompt 溢位會執行一次壓縮 callback，然後重試。
- 反覆的過載可以觸發 fallback model。
- 未知或不可重試的錯誤會被拋出。

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

溢位會在一般狀態處理之前先檢查。如果壓縮能縮小 prompt，`prompt_too_long` 錯誤就是可復原的。

```python
def _status(e):
    return getattr(e, "status_code", None)

def _is_overflow(e) -> bool:
    return getattr(e, "overflow", False) or "prompt is too long" in str(e).lower()
```

`with_retry` 持有每次嘗試的狀態：

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

迴圈把它的模型呼叫包起來：

```python
response = recovery.with_retry(
    lambda: model(messages, registry, system),
    on_overflow=lambda: _reactive_trim(messages),
    fallback_model=fallback_model)
```

- Recovery 只包住模型呼叫。
- `_reactive_trim` 就地修改 `messages[]`，供一次溢位重試使用。
- 當 recovery 放棄時，錯誤會被浮現出來，而不是被藏起來。

---

## 各系統做法

Recovery 包住模型呼叫。迴圈主體維持不變。

| System | Retry | Token handling | Model fallback |
| --- | --- | --- | --- |
| **Claude Code** | 由狀態決定、帶退避的重試。 | 提高輸出 token、續寫，或壓縮。 | 反覆過載後改用 fallback。 |

### Claude Code

- `withRetry` 會重試 429、408、409 和 5xx 錯誤。
- `retry-after` 優先於計算出來的退避。
- 對背景來源的 529 重試次數有限制。
- 輸出被截斷時，可以用更高的輸出上限重試。
- 續寫 prompt 能救回一些 `max_tokens` 的停止。
- Reactive compaction 處理 `prompt_too_long`。
- 反覆的 529 可能拋出 `FallbackTriggeredError`。

> **取捨：** 針對性的復原路徑救回的執行比一概重試更多。它們也多了更多要維護的分支與界限。

---

## 失效模式

- **Retry storm：**許多 client 同時對過載重試會讓負載更糟。限制重試次數並尊重 `retry-after`。
- **無限復原：**提高上限、續寫和壓縮都可能無限迴圈。為每條路徑設界限。
- **溢位無法縮小：**如果一次 reactive compaction 失敗，就停止，而不是永無止境地壓縮。
- **錯誤消失：**一個被吞掉的錯誤會讓 transcript 少了結果。在復原用盡之後，把失敗浮現出來。
- **Stop hook 重播 API 錯誤：**對 API 錯誤訊息略過 stop hook。

---

## 可執行程式

[`src/`](src/) 承接 10 並加入：

- [`recovery.py`](src/recovery.py)：重試分類、退避、溢位處理，以及 fallback 觸發。
- [`loop.py`](src/loop.py)：把它的模型呼叫包在 `with_retry` 裡。
- [`test.py`](src/test.py)：用一個假的不穩定呼叫驅動每一條路徑。
- [`demo.py`](src/demo.py)：在一次 live 執行中注入一次模擬過載。

```bash
python sections/11-error-recovery/src/test.py         # offline checks, no key
uv run python sections/11-error-recovery/src/demo.py  # live demo, needs a key
```

---

## 出處

- Claude Code 原始碼：`services/api/withRetry.ts`、`query.ts`、`services/api/claude.ts`、`services/api/errors.ts`、`query/tokenBudget.ts`、`utils/context.ts`。
- learn-claude-code · s11_error_recovery：章節框架。
