# 20 · Observability & evaluation

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 你看不見的東西修不好，沒人記下來的 run 也沒辦法評分。

一個 agent 無人看管地運行、產生副作用，還花錢。一次模型呼叫是個黑盒子：它燒 token，並觸發真實的動作。

沒有 instrumentation，你連最基本的問題都答不出來。它做了什麼。某個工具失敗了幾次。這個 session 花了多少錢。

這一章負責的是紀錄：每趟 run 一棵 trace、花掉的錢算得出是哪個任務花的、event 乾淨到可以存起來也可以拿出去給別人看。

一次改動讓品質變好還是變差，那是另一件事，現在有自己的一章（第 23 章）。它吃的就是這一章記下來的東西。

紀錄不做，成本暴衝每次都是意外，bug 回報一份都重現不了，eval 集也拿不到任何真實素材。

---

## 機制

![機制圖](assets/20-observability.png)

兩條可分離的 pipeline，都不碰 loop 的控制流。

telemetry 直接在 loop 裡跑：每一步都呼叫一次 logger，呼叫完不等結果（fire and forget）。

event 的去處叫 sink，可能是終端機、檔案，或 Datadog 這類 backend。event 先排在佇列裡，等某個 sink 接上，再經過採樣、洗掉敏感欄位，最後送給每一個 sink。

evaluation 離線跑，用的是它自己的 task 集（第 23 章）。那些 task 就是從這一章來的。

- `emit` 永不阻塞、永不拋例外，所以一次 logging 故障無法卡住或弄垮 loop（第 1 章）。
- event 會先在佇列裡緩衝，等某個 sink 接上再一次送出，所以 loop 在 telemetry 就緒之前就能 log。
- 採樣依速率丟棄 event；scrub 只保留白名單欄位，所以程式碼與路徑永不外洩。
- 每個 event 帶一個 parent 連結，扁平的事件流就變成每趟 run 一棵樹，跑完之後才讀得懂。
- 成本按模型累加成一個 USD 總額，也按任務各自累加，這樣單獨一趟失控的 run 才不會被平均掉。
- 失敗和特別貴的 run，trace 脫敏之後變成 eval task，離線套件才跟得上正式環境真正會遇到的東西。

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

### 用 span，不是扁平事件

扁平的事件流只說得出「有這麼一次呼叫」，說不出這次呼叫屬於哪一步。一個請求會散成好幾次模型呼叫、工具呼叫和檢索，
有的巢狀、有的並行，事後想靠時間戳拼回去，只能用猜的。

一趟 run 是一條 trace，裡面每一件工作是一個 span。每個 span 帶開始時間、耗時、狀態，還有它 parent 的 id，所以一趟 run 的 span 會長成一棵樹。
從樹頂往下讀，就知道哪一步失敗、哪一步慢、每一棵子樹各花了多少錢。

撐起這件事的是兩套慣例。OpenTelemetry 定義 span 本身：trace id、parent 連結、時間、狀態、attribute。
OpenInference 再往上補 LLM 專用的 attribute 名稱：prompt、completion、model、token 數、工具呼叫。
照這套名稱埋一次點，換 backend 就只是部署上的選擇，不用重寫。

匯出跟 `emit` 一樣不能落在熱路徑上。span 先排隊，由背景 worker 分批送出，所以 collector 慢下來，run 一點都不受影響。
這一章的 `emit` 就是這一切的扁平版；在同一批 event 上補一個 trace id 和一個 parent span id，升級就完成了。

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

- `add` 查出每 token 的定價，並把花費滾進 `cost_usd`，也就是即時與退出時顯示的那個數字。
- 這個總額是最粗的那個有用數字。它說得出這個 session 花了多少，說不出是哪個任務花的。

agent 的成本不會跟著步數線性長。每一輪都要把整段對話重送一次，所以第二輪回傳的工具結果，到第三、第四、第五輪還要再被計費一次。
context 每長出一段，後面每一輪都得再付一遍，所以總花費爬升的速度比較接近輪數的平方，不是輪數本身。
prompt caching（第 10 章）和 compaction（第 8 章）各砍掉其中一塊，但兩邊省下來的不能相加：compaction 拿掉的，正好是 caching 本來就會打折的那些 token。

所以成本要算到任務層級，不能只算 session，而且要按任務設上限。碰到上限就把這趟 run 停掉，跟步數上限攔下停不下來的 loop 是同一招（第 1 章）。
書裡講這套成本模型時沒有引外部來源，所以把這個形狀當成作者自己的現場經驗，不是量出來的曲線。

這一章原始碼裡的 `run_eval` 是最小規模的 eval：把一組固定的 task 集重播到候選 build 上，數過了幾題，回傳一個比率。
第 23 章在同一個入口下面補上環境、模擬使用者和重複執行，也講清楚為什麼比率小幅下滑通常是雜訊，不是 regression。

### trace 回流成 eval 集

兩條 pipeline 只在一個方向上交會：正式環境的 trace 變成 eval task。

- **篩。**留下值得學的那幾趟：報錯的、使用者重試或出手糾正的、花費遠高於中位數的。一趟順順利利的 run，套件從裡面學不到新東西。
- **脫敏。**擋住程式碼和路徑不進 backend 的那份白名單，同樣擋住它們進 task 檔。task 集裡帶著客戶的路徑，就沒辦法拿給需要跑它的人。
- **重播。**trace 裡有起始狀態和每一次工具呼叫，所以它拼得回一個 task：這個狀態、這個請求、本來應該出現的這個結果。

這件事持續做，eval 集才跟得上線上的真實分布，而不是一開始有人憑感覺猜的那個分布。落到這裡的東西，由第 23 章來評分。

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

每個 agent 如何發出 telemetry、追蹤花費，以及怎麼餵養 eval 集。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 低成本又安全地換來豐富的正式環境可見度。壞掉的 sink 卡不住也弄不垮 loop。 | crash 掉的 run 也留得下可重建的檔案。軌跡檔既是稽核紀錄，也是 eval 語料。 |
| **Cons** | 只告訴你發生了什麼，答案好不好看不出來。event 是扁平的，一趟 run 得自己手動拼回去。 | 正式環境 telemetry 幾乎沒有，run 進行中沒有 event 流可看。 |
| **Why** | 正式環境得盯住當機和成本暴衝，而且 telemetry 不能碰 loop 的控制流。 | 品質靠離線 benchmark 評分，所以每趟 run 的完整紀錄比即時 event 更重要。 |
| **How: telemetry** | event 先排隊，等 sink 接上再採樣、scrub，送給每個 sink。 | 每趟 run 一個軌跡檔：完整訊息歷史加 config、成本、exit status，每一步都存。 |
| **How: cost tracking** | 每模型 token 按定價滾進一個 session USD 總額，退出時印出。 | litellm 逐次計價，彙總成 run 與全域總額；沒定價的模型預設直接報錯。 |
| **How: eval feed** | 原始碼中沒有；為重建。一般做法：trace 脫敏後變成 regression 案例。 | 存下來的軌跡就是語料；repo 內建的 benchmark runner 為一整組 task 評分。 |

---

## 哪裡會出錯

- **telemetry 落在熱路徑上：**一個會阻塞或拋例外的 logging 呼叫會卡住 loop（第 1 章），一個要等網路回應的 span exporter 也一樣。
  緩解：呼叫完不等結果，搭配 pre-sink 佇列、每 sink killswitch，以及背景 worker 分批匯出。
- **敏感資料洩漏到 log：**程式碼、檔案路徑或 prompt 落進一個一般存取的 backend，或落進由 trace 生出來的 task 檔。
  緩解：白名單可記錄欄位，送出或存檔之前 scrub 掉其餘。
- **扁平事件流沒有 parent 連結：**沒人說得出哪次模型呼叫屬於哪一步，一趟失敗的 run 只能靠時間戳重新拼。
  緩解：每個 event 都帶 trace id 和 parent span id，用 backend 本來就認得的命名慣例。
- **成本漂移沒被察覺：**一次模型替換或失控 loop 會讓花費倍增，而一個 session 總額會蓋掉那個真正在燒錢的任務。
  緩解：每模型與每任務的總額都即時和退出時顯示，加上每任務的上限，還有 loop 的步數上限（第 1 章）。
- **eval 集跟正式環境脫節：**離線 task 漏掉了真實用法，於是套件通過而使用者失敗（第 23 章）。
  緩解：持續把失敗和昂貴的 run 脫敏之後篩進 task 集。

---

## 可執行程式

[`src/`](src/) 承接第 19 章並加上：

- [`telemetry.py`](src/telemetry.py)：event logger（`Telemetry.emit`、排隊與送出、`sample`、`scrub`）、每模型的 `CostTracker`，以及離線的 `run_eval`。
- [`test.py`](src/test.py)：先排隊再送出、採樣、scrub 加上真實工具 dispatch 上的 sink 隔離、每模型成本，以及一個抓到退步 build 的 eval。
- [`demo.py`](src/demo.py)：一輪 agent 由掛在 model wrapper 上的 telemetry 觀察、一個即時 session 成本，接著一個離線 eval。

loop 與 dispatch 都不變。telemetry 從外部觀察，而被它餵養的 eval 在熱路徑之外跑（第 23 章）。

```bash
python sections/20-observability/src/test.py         # offline checks, no key
uv run python sections/20-observability/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code analytics](https://github.com/yasasbanukaofficial/claude-code)：
  `services/analytics/index.ts`（queue + `logEvent`）、`sink.ts`、`datadog.ts`、`firstPartyEventLogger.ts`、`sinkKillswitch.ts`、`shouldSampleEvent`。
- [Claude Code cost and diagnostics](https://github.com/yasasbanukaofficial/claude-code)：
  `cost-tracker.ts`、`utils/modelCost.ts`、`costHook.ts`（`formatTotalCost`）、`diagnosticTracking.ts`、`upstreamproxy/relay.ts`。
- [ai-agent-book](https://github.com/bojieli/ai-agent-book)：`book/chapter6.md`，以中文原書為準。
  span 樹、非線性的 agent 成本與每任務上限，還有正式環境 trace 回流成 eval 集。
  書裡的成本分析沒有引用外部來源，屬於單一來源。
- [OpenTelemetry tracing](https://opentelemetry.io/docs/specs/otel/trace/api/)：span 本身、parent 連結、時間、狀態與 attribute。
- [OpenInference](https://github.com/Arize-ai/openinference)：在 span 上替 LLM 與工具 attribute 命名的語意慣例。
- evaluation 不在 Claude Code 這份原始碼裡，在這個 repo 由第 23 章負責。保留的 task 集與 LLM-as-judge 仍以重建與一般做法描述。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`agents/default.py`、`models/__init__.py`、`run/benchmarks/swebench.py`、`run/utilities/inspector.py`。
- 章節定位：[learn-claude-code · s20_comprehensive](https://github.com/shareAI-lab/learn-claude-code)。
