# 11 · Error recovery

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 先分類失敗，再重試、調整，或停止。

一次 agent 執行可能橫跨很多次模型呼叫。任何一次呼叫都可能因為網路問題、過載、rate limit、輸出上限或 context overflow 而失敗。

模型呼叫只是其中一層。有人研究了生產環境的 coding agent，把失敗分成四層：API、tool、context、control flow。
API 層是 timeout、rate limit 和過載。tool 層是指令回傳非零，或 handler 拋出例外。
context 層是 prompt overflow 和壞掉的訊息歷史。control flow 層是一直重複、卻沒有任何進展的步驟。
先判斷是哪一層，再開始數次數。計數器要是在分類之前就跑起來，預算就會花在重試根本救不了的錯誤上。

loop 對不同的失敗需要不同的回應：

1. 對暫時性錯誤重試。
2. 當問題出在 prompt 或輸出上限時，調整後再重試。
3. 當錯誤無法復原時，停止。

沒有復原機制，一次暫時的 API 失敗就能終結一項長時間的任務。

---

## 機制

![機制圖](assets/11-error-recovery.png)

把模型呼叫包在一個重試輔助函式裡。這個輔助函式先分類失敗，再採取一個有界限的行動。

- 暫時性的狀態碼會退避後重試。
- prompt overflow 會執行一次壓縮 callback，然後重試。
- 反覆的過載可以觸發 fallback model。
- 未知或不可重試的錯誤會被拋出。

### New: 分類、backoff 與 retry helper

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

overflow 會在一般狀態處理之前先檢查。如果壓縮能縮小 prompt，`prompt_too_long` 錯誤就是可復原的。

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

### 如何整合

loop 把它的模型呼叫包起來：

```python
response = recovery.with_retry(
    lambda: model(messages, registry, system),
    on_overflow=lambda: _reactive_trim(messages),
    fallback_model=fallback_model)
```

- Recovery 只包住模型呼叫。
- `_reactive_trim` 就地修改 `messages[]`，供一次 overflow 重試使用。
- 當 recovery 放棄時，錯誤會被浮現出來，而不是被藏起來。

### 模型呼叫以外的部分

上面這個 helper 只顧到 API 這一層。另外三層各自需要自己的檢查。

**沒有進展。** 每次 tool call 都用「名稱加參數」做成一個 fingerprint。fingerprint 一直重複，就代表 agent 在做同一件事，而且什麼也沒學到。
步數上限最後也會攔下來，但那時預算已經燒完了。fingerprint 計數器幾步之內就能發現，而且說得出是哪一次呼叫卡住。
每條復原路徑也各自配一個失敗計數器，這樣一直失敗的那條路會自己跳閘，不用等到全域上限。

**沒有活性。** connect timeout 看不到「連上了、然後就沒聲音」的 stream。旁邊再跑一個 idle watchdog，時間窗內沒有 token 進來就取消這次呼叫。
接著 retry helper 就把這次取消當成一般的暫時性失敗來處理。

**歷史壞掉。** 一輪中途 crash，可能留下一個沒有對應 `tool_result` 的 `tool_use` block。下一次請求會卡在訊息格式，而不是卡在工作本身。
送出之前先把成對關係修好。至於「修」是什麼意思，得看這份 transcript 是拿來做什麼的。
產品用的 harness 會塞一個 placeholder 結果，寫明這次呼叫被中斷，讓執行繼續下去。
拿來錄訓練資料的 harness 則拒絕修補，因為造一個假結果，等於教模型一個根本沒發生過的步驟。

### 復原要分級

復原不是一個決定。要照呼叫端該看到多少來分級。

1. 安靜重試。呼叫端只看得到最後的結果。
2. 降級後繼續。回傳一個縮水的結果，並說清楚少了什麼。
3. 把失敗浮現出來，附上試過哪些方法，讓模型可以換一條路走。

前兩級產生的錯誤要隔離起來。先押在 helper 裡面，等復原真的放棄了才放出去。
中間過程的錯誤一旦傳到模型面前，模型會當成最終結果，可能因此重做一件其實已經成功的工作。

復原也可能自己餵自己。錯誤路徑上要是還會觸發帶副作用的邏輯（hook、摘要、通知），那就又去呼叫一次模型，然後又失敗一次。
在錯誤路徑上把那些邏輯關掉，另外帶一個遞迴深度計數器，把漏網的鏈條切斷。
背景呼叫則完全不重試。它們不在關鍵路徑上，重試只會把主 loop 需要的額度花掉。

界限要照實際量到的失敗來訂，不是靠直覺。有一份執行紀錄顯示，同一條復原路徑失敗了三千多次，
這類 loop 一天大約吃掉二十五萬次 API 呼叫。壓縮試三次就停，這個界限就是這樣量出來的。
這些數字只有單一來源，看的時候要當成某個實作在某一段時期的樣子。

---

## 各系統做法

Recovery 包住模型呼叫。loop 主體維持不變。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 針對性的復原路徑救回的 run 比一概重試更多。 | 只有三條路徑要維護。就算 crash，硬碟上也留有完整軌跡。 |
| **Cons** | 要維護的分支與界限更多。 | 救回的 run 較少。context overflow 直接中止，連續三次格式錯誤也會結束 run。 |
| **Why** | 一次暫時的 API 失敗不該終結長任務。 | 只留三條路：暫時性錯誤就重試、格式錯誤還給模型、其餘帶著具名狀態退出。 |
| **How: retry** | 帶退避重試 429、408、409 和 5xx，`retry-after` 優先。 | tenacity 退避 4 到 60 秒，最多 10 次。救不回的錯誤直接跳過。 |
| **How: token handling** | 提高輸出 token、在`max_tokens` 停止後續寫，或在 `prompt_too_long` 時壓縮。 | 沒有，context overflow 直接中止 run。 |
| **How: model fallback** | 反覆過載（529）後改用 fallback。背景來源的 529 重試次數有限制。 | 沒有。 |

---

## 哪裡會出錯

- **Retry storm：**許多 client 同時對過載重試會讓負載更糟。限制重試次數並尊重 `retry-after`。
- **無限復原：**提高上限、續寫和壓縮都可能無限 loop。為每條路徑設界限。
- **overflow 無法縮小：**如果一次 reactive compaction 失敗，就停止，而不是永無止境地壓縮。
- **錯誤消失：**一個被吞掉的錯誤會讓 transcript 少了結果。在復原用盡之後，把失敗浮現出來。
- **Stop hook 重播 API 錯誤：**對 API 錯誤訊息略過 stop hook。
- **卡住了，卻沒有錯誤：**一直重複同一個呼叫不會拋出任何東西，重試路徑一條也不會啟動。數重複的 tool 加參數 fingerprint，把 loop 打斷。
- **stream 靜靜停住：**連上之後就沒聲音的 stream，是過得了 connect timeout 的。跑一個 idle watchdog，直接取消這次呼叫。
- **修補污染了紀錄：**塞一個 placeholder `tool_result` 能讓產品環境的執行活下去，但也記下了一個根本沒跑過的步驟。transcript 要拿去當訓練資料時就別修。
- **中間錯誤外洩：**復原還沒結束就先送出去的錯誤，會被當成最終結果，害人白做一輪工。先隔離起來，等復原放棄了再說。

---

## 可執行程式

[`src/`](src/) 承接 10 並加入：

- [`recovery.py`](src/recovery.py)：重試分類、退避、overflow 處理，以及 fallback 觸發。
- [`loop.py`](src/loop.py)：把它的模型呼叫包在 `with_retry` 裡。
- [`test.py`](src/test.py)：用一個假的不穩定呼叫驅動每一條路徑。
- [`demo.py`](src/demo.py)：在一次 live 執行中注入一次模擬過載。

```bash
python sections/11-error-recovery/src/test.py         # offline checks, no key
uv run python sections/11-error-recovery/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code 原始碼](https://github.com/yasasbanukaofficial/claude-code)：
  `services/api/withRetry.ts`、`query.ts`、`services/api/claude.ts`、`services/api/errors.ts`、`query/tokenBudget.ts`、`utils/context.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：
  `models/utils/retry.py`、`models/litellm_model.py`、`agents/default.py` 的 `run()` 與 `max_consecutive_format_errors`。
- [ai-agent-book · 第 5 章](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter5.md)（《深入理解 AI Agent》，李博杰，以中文原版為準）：
  四層失敗分類、用 tool 加參數做 loop fingerprint、idle watchdog、`tool_result` 成對修補以及產品與訓練資料兩套標準、
  分級復原加錯誤隔離，還有防死亡螺旋的那幾招。它的註腳 ch5-3 說這套分類來自對生產環境 agent 的研究（其中包含 Claude Code），
  也提醒實作變動很快。三千多次失敗的那份紀錄、以及一天二十五萬次呼叫這兩個數字，是書中作者自己的生產數據，只有單一來源。
- [learn-claude-code · s11_error_recovery](https://github.com/shareAI-lab/learn-claude-code)：章節框架。
