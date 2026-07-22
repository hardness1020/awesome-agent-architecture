# 20 · Observability & evaluation

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 你無法修好你看不見的東西，也無法信任你從未量測過的東西。

一個 agent 無人看管地運行、產生副作用，還花錢。一次模型呼叫是個黑盒子：它燒 token，並觸發真實的動作。

沒有 instrumentation，你連最基本的問題都答不出來。它做了什麼。某個工具失敗了幾次。這個 session 花了多少錢。上一次發佈是否變差了。

有兩項工作能回答這些問題。observability 監看正式環境：每一步一個 event、追蹤花費、可重建的 run。evaluation 判斷一次變更讓品質變好還是變差。

兩者都不做，那麼每次 regression 都會無聲上線，每次成本暴衝都是意外，而每份 bug 回報都無法重現，因為什麼都沒被記錄下來。

---

## 機制

![機制圖](assets/20-observability.png)

兩條可分離的 pipeline，都不碰 loop 的控制流。

telemetry 直接在 loop 裡跑：每一步都呼叫一次 logger，呼叫完不等結果（fire and forget）。

event 的去處叫 sink，可能是終端機、檔案，或 Datadog 這類 backend。event 先排在佇列裡，等某個 sink 接上，再經過採樣、洗掉敏感欄位，最後送給每一個 sink。

evaluation 離線運行：把一組固定的 task 集重播到某個候選 build 上，並為每個輸出評分。

- `emit` 永不阻塞、永不拋例外，所以一次 logging 故障無法卡住或弄垮 loop（第 1 章）。
- event 會先在佇列裡緩衝，等某個 sink 接上再一次送出，所以 loop 在 telemetry 就緒之前就能 log。
- 採樣依速率丟棄 event；scrub 只保留白名單欄位，所以程式碼與路徑永不外洩。
- 成本按模型累加成一個 USD 總額，即時顯示並在退出時顯示。
- eval 在熱路徑之外：它為一組固定的 task 集評分，所以一次悄悄的品質下滑會在使用者遇到之前被抓到。

### New: fire-and-forget 事件記錄

`telemetry.py` 發出 event。event 先排在佇列裡，等某個 sink 接上，再採樣、scrub，送給每一個 sink。`emit` 永不拋例外：

```python
def emit(self, name, **meta):                          # src/telemetry.py
    if not self.sinks:
        self._queue.append((name, meta))               # buffer until a sink is ready
        return
    self._deliver(name, meta)

def _deliver(self, name, meta):
    if not self.sample(name):                          # dropped by sampling rate
        return
    clean = scrub(meta)                                # allowlist before any backend sees it
    for sink in self.sinks:
        try:
            sink(name, clean)
        except Exception:                              # one bad sink never breaks the loop
            pass
```

- 在任何 sink 接上之前，event 會在 `_queue` 裡緩衝；`attach` 透過同一條 `_deliver` 路徑把它們全部送出去，所以排隊的 event 同樣會被採樣與 scrub。
- `scrub` 只保留 `SAFE_FIELDS`，所以一個未知安全的值（程式碼、檔案路徑、prompt）永遠不會抵達 backend。
- 一個拋例外的 sink 會被吞掉，所以一個壞掉的 backend 無法卡住或弄垮 loop。

### New: 每個模型的成本與離線 eval

成本按模型累加成一個滾動的 USD 總額：

```python
def add(self, model, input_tokens, output_tokens):    # src/telemetry.py
    i, o = self.by_model.get(model, (0, 0))
    self.by_model[model] = (i + input_tokens, o + output_tokens)
    pi, po = PRICES.get(model, (0.0, 0.0))             # modelCost.ts pricing tiers
    self.cost_usd += input_tokens * pi + output_tokens * po
    return self.cost_usd
```

而 evaluation 把一組固定的 task 集重播到某個候選 build 上，並為每個輸出評分：

```python
def run_eval(build, tasks):                            # src/telemetry.py
    verdicts = [bool(grade(build(inp))) for inp, grade in tasks]
    passed = sum(verdicts)
    return {"passed": passed, "total": len(tasks), "rate": passed / len(tasks), "verdicts": verdicts}
```

- `add` 查出每 token 的定價，並把花費滾進 `cost_usd`，也就是即時與退出時顯示的那個數字。
- `run_eval` 用各自的評分準則為每個輸出評分，並回傳一個 pass rate；一個退步的 build 分數較低，這就是發佈訊號。
- 這兩條 pipeline 共用一套詞彙（event 名稱、成本單位），所以一個漂移的 metric 能對應回一個本該抓到它的 eval。

### 如何整合

demo 把 telemetry 掛在 model wrapper 上。loop 不變：

```python
def model(messages, registry, system):
    r = client.messages.create(...)
    cost.add(MODEL, r.usage.input_tokens, r.usage.output_tokens)   # cost rollup
    tel.emit("model_call", model=MODEL, tokens=..., cost_usd=...)  # scrubbed event
    return r
run_turn([...goal...], lambda m, r, s: model(m, r, SYSTEM), reg, Session(mode=DEFAULT))   # the one agent call
```

- telemetry 從外部觀察：wrapper 發出一個 event 並追蹤成本，所以 `run_turn` 與 dispatch 與第 13 章逐位元組相同。
- sink 印出每個 event；session 成本在最後印出；接著一個離線 `run_eval` 為一組固定的 task 集評分。
- 上游的一切都不變。observability 是一個旁觀者，不是 loop 裡的一個新步驟。

---

## 各系統做法

每個 agent 如何發出 telemetry、追蹤花費、量測品質。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 低成本又安全地換來豐富的正式環境可見度。壞掉的 sink 卡不住也弄不垮 loop。 | crash 掉的 run 也留得下可重建的檔案。軌跡檔既是稽核紀錄，也是 eval 語料。 |
| **Cons** | 只告訴你發生了什麼，答案好不好看不出來。原始碼沒帶 eval，抓不到悄悄的品質 regression。 | 正式環境 telemetry 幾乎沒有，run 進行中沒有 event 流可看。 |
| **Why** | 正式環境得盯住當機和成本暴衝，而且 telemetry 不能碰 loop 的控制流。 | 品質靠離線 benchmark 評分，所以每趟 run 的完整紀錄比即時 event 更重要。 |
| **How: telemetry** | event 先排隊，等 sink 接上再採樣、scrub，送給每個 sink。 | 每趟 run 一個軌跡檔：完整訊息歷史加 config、成本、exit status，每一步都存。 |
| **How: cost tracking** | 每模型 token 按定價滾進一個 session USD 總額，退出時印出。 | litellm 逐次計價，彙總成 run 與全域總額；沒定價的模型預設直接報錯。 |
| **How: evaluation** | 原始碼中沒有；為重建。一般做法：一組保留的 task 集按 build 評分。 | repo 內建 SWE-bench batch runner，每個 instance 一個 Docker 容器；中斷的 batch 可以續跑。 |

---

## 哪裡會出錯

- **telemetry 落在熱路徑上：**一個會阻塞或拋例外的 logging 呼叫會卡住 loop（第 1 章）。緩解：呼叫完不等結果，搭配 pre-sink 佇列與每 sink killswitch。
- **敏感資料洩漏到 log：**程式碼、檔案路徑或 prompt 落進一個一般存取的 backend。緩解：白名單可記錄欄位，送出前 scrub 掉其餘。
- **成本漂移沒被察覺：**一次模型替換或失控 loop 會讓花費倍增。緩解：即時與退出時顯示每模型總額，加上 loop 的步數上限（第 1 章）。
- **沒有 regression 訊號：**沒有一套 eval，一次 prompt 或 harness 變更就上線，品質默默下滑。緩解：一組保留的 task 集按 build 評分，作為發佈的閘門。
- **eval 與正式環境不符：**離線 task 漏掉了真實用法，於是套件通過而使用者失敗。緩解：從 scrub 過的 trace 播種 task，讓兩者共用同一個分布。

---

## 可執行程式

[`src/`](src/) 承接第 19 章並加上：

- [`telemetry.py`](src/telemetry.py)：event logger（`Telemetry.emit`、排隊與送出、`sample`、`scrub`）、每模型的 `CostTracker`，以及離線的 `run_eval`。
- [`test.py`](src/test.py)：先排隊再送出、採樣、scrub 加上真實工具 dispatch 上的 sink 隔離、每模型成本，以及一個抓到退步 build 的 eval。
- [`demo.py`](src/demo.py)：一輪 agent 由掛在 model wrapper 上的 telemetry 觀察、一個即時 session 成本，接著一個離線 eval。

loop 與 dispatch 都不變。telemetry 從外部觀察；eval 在熱路徑之外運行。

```bash
python sections/20-observability/src/test.py         # offline checks, no key
uv run python sections/20-observability/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code analytics](https://github.com/yasasbanukaofficial/claude-code)：`services/analytics/index.ts`（queue + `logEvent`）、`sink.ts`、`datadog.ts`、`firstPartyEventLogger.ts`、`sinkKillswitch.ts`、`shouldSampleEvent`。
- [Claude Code cost and diagnostics](https://github.com/yasasbanukaofficial/claude-code)：`cost-tracker.ts`、`utils/modelCost.ts`、`costHook.ts`（`formatTotalCost`）、`diagnosticTracking.ts`、`upstreamproxy/relay.ts`。
- evaluation 不在這份原始碼裡。eval harness、SWE-bench 風格的套件，以及 LLM-as-judge，均以重建與一般做法描述。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`agents/default.py`、`models/__init__.py`、`run/benchmarks/swebench.py`、`run/utilities/inspector.py`。
- 章節定位：[learn-claude-code · s20_comprehensive](https://github.com/shareAI-lab/learn-claude-code)。
