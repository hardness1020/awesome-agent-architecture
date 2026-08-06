# 2 · Tool runtime

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 新增一項能力，就是註冊一個工具。loop 維持不變。

agent loop 只能透過工具來行動。模型會發出一個結構化的 `tool_use` 區塊，帶有 `name` 與 `input`。

harness 把那個名稱對應到程式碼。它驗證輸入、執行 handler，並回傳結果。

這個 runtime 必須：

1. 告訴模型有哪些工具存在。
2. 描述每個工具的 input schema。
3. 依名稱把每個 `tool_use` 路由出去。
4. 在可行時平行執行安全的呼叫。
5. 讓龐大的工具目錄仍可被探索。

沒有這一層，模型能要求行動，卻沒有東西能真正執行那個行動。

如果只有一個 `bash` 工具，每一項能力都變成字串處理。沒有各別工具的驗證或權限邏輯。

有兩種失敗常被算到模型頭上，其實都是從這一層開始的。兩份 description 彼此重疊，模型就挑錯工具。harness 半路改寫了 input，編輯就失敗。

---

## 機制

![機制圖](assets/02-tool-runtime.png)

一個工具是一個小物件，帶有名稱、handler、schema 與幾個判定式。registry 依名稱存放工具。dispatch 拿名稱去查表，找到就執行。

### New: the tool runtime

```python
@dataclass
class Tool:                                  # src/tools.py
    name: str
    run: Callable[[dict], Any]
    description: str = ""                      # advertised to the model
    input_schema: dict = ...                   # the Anthropic schema it accepts
    is_read_only: bool = False
    is_concurrency_safe: bool = False         # may batch in parallel
    is_edit: bool = False                     # read by the gate (section 3)

class Registry:                              # src/tools.py
    def register(self, tool): self._tools[tool.name] = tool   # add a handler
    def get(self, name):      return self._tools.get(name)    # dispatch = lookup
    def schemas(self):        ...             # the tools list handed to the model
```

- 一個工具是一個 dataclass。
- registry 是 `name -> tool`。
- 新增一項能力，就是註冊一個 handler。
- `schemas()` 回傳向模型公告的工具清單。
- `run_concurrently` 會把標記為 `is_concurrency_safe` 的工具批次執行。
- 不安全的呼叫維持依序執行，所以寫入不會相互競爭。

### How it integrates

第 1 章用的是內嵌的 `HANDLERS` dict。第 2 章把一個 `registry` 傳進 loop，並把每個 `tool_use` 透過 `_dispatch` 路由：

```python
def run_turn(messages, model, registry, max_steps=10): # src/loop.py (now takes a registry)
    ...
    results = [_dispatch(b, registry)                   # was: run_tool(call)
               for b in response.content if b.type == "tool_use"]
    messages.append({"role": "user", "content": results})

def _dispatch(block, registry):              # resolve, run, wrap as a tool_result
    tool = registry.get(block.name)           # name -> tool
    content = run_tool(tool, block.input)
    return {"type": "tool_result", "tool_use_id": block.id, "content": content}
```

loop 主體其餘部分維持不變。只有 dispatch 這一步現在改用 registry。

`_dispatch` 是下一個延伸點。第 3 章在那裡加上權限關卡。第 4 章在那裡加上 hook。

demo 為了清楚起見採依序 dispatch。真實的 runtime 會把安全呼叫批次化，並隨需載入龐大的工具 schema。

### 延伸閱讀

底下這些設計，`src/` 裡都沒有實作。它們來自 ai-agent-book 對正式環境 agent 的記述，還有已發表的工具使用研究。
把它們當成別人寫下來的做法就好，別當成下面表格那些系統經過確認的行為。
文中點名 Claude Code 的地方，是拿它自己的原始碼來對照，出處列在最後。

**分類。**扁平的 registry 看不出一份目錄長什麼樣子。工具依呼叫往哪裡去、又碰到什麼，可以分成五類。
感知讀外面的世界，執行改動它，協作找上另一個 agent，事件觸發讓外界把 agent 叫醒，跟使用者溝通則是找上人。
第 6、12、16 章做協作，第 13、14 章做事件觸發，第 19 章做跟使用者溝通的管道。這一章做的是這五類共用的那一層。

**粒度。**兩個工具做的事情差不多、吃的輸入也差不多，就合併起來。一個 `read_document` 帶一個型別參數，比每種檔案格式各配一個讀取工具好用。
參數開始不一樣了就拆開。一份 schema 如果把互不相干的欄位全湊在一起，它講不出哪些欄位該填，模型就會填錯。

**description 怎麼寫。**`description` 不是文件。模型在挑工具之前，能看的只有它。寫得好的會講清楚什麼時候該用、什麼時候不該用，
給出真實的參數值、回傳長什麼樣，還有呼叫一次要花多少代價。與其再多寫一段說明，不如附幾個實際的呼叫例子。
書裡說加了例子效果提升很多，但那個數字沒有出處，所以只取方向，別當成量級。

**參數保真。**harness 要把 input 原封不動交給 handler。假設它把引號正規化了、把空白修掉了，或多塞了一個模型根本沒寫的參數，
這次呼叫就會壞在模型看不到的地方。它送出去的 input 是對的，結果卻說編輯沒對上，transcript 裡也找不到任何解釋。
輸入不合法就拒絕，並講明理由。不要自己動手改。

**檢查用參數。**有些參數存在就是為了被忽略。像 `expected_price` 這種參數，逼模型在呼叫真的跑起來之前，先把它以為的數字寫下來。
handler 不會照那個數字做事。它讀的是存起來的值，決定也照那個值下，兩邊對不上就記一筆。
這樣最後一道檢查站的就是模型偽造不了的資料。τ-bench 的評分也是這樣：看資料庫最後的狀態，不看 agent 自己說它做了什麼。

**感知工具的介面。**感知工具找到的東西，通常比 context 裝得下的還多。有三條規則能讓結果誠實。
搜尋一次只回一頁候選，外加一個 cursor。讀取吃 offset 和 limit，模型才走得完一個長檔案。截斷要標在結果裡。
默默截掉比直接報錯更糟，因為模型會把一份殘缺的檔案當成完整的在讀。

程式碼搜尋最能看出這個取捨。四種做法，而且沒有系統只用其中一種：

| 做法 | 找得到什麼 | 代價 |
| --- | --- | --- |
| **Glob** | 依路徑樣式找檔案。 | 對內容一無所知。 |
| **Grep** | 精確字串和 regex，附行號。 | 要呼叫好幾次才收斂。同義詞找不到。 |
| **Embedding 索引** | 依語意找程式碼，用白話問也問得到。 | 索引要建、還要一直同步。排序說不清楚。 |
| **LSP symbols** | 定義、參照、型別，一找一個準。 | 每種語言都要一個 language server。 |

Claude Code 不建索引。它一步一步搜：先 glob、再 grep、然後讀檔，模型在每次呼叫之間把查詢收窄。
書裡描述 Cursor 走的是另一條路，花成本建索引，好讓一句白話查詢也能找到沒有指名任何識別字的程式碼。

編輯這邊也一樣分岔。要講清楚改了什麼，有五種寫法：

| 方案 | 模型送出什麼 | 取捨 |
| --- | --- | --- |
| **diff 加 apply model** | 一份粗略的骨架 diff，再由第二個訓練過的 model 改寫。 | 快，也容錯。但得多養一個 model。 |
| **舊字串換新字串** | 要找的原文，以及要換上去的文字。 | 沒有歧義，錯了會直接報錯。前提是先讀過檔案。 |
| **行號** | 一段行號範圍加上替換內容。 | 很省字。但前面一改，行號就過期。 |
| **編輯器指令** | 一套小型指令語言，vim 那種。 | 很精簡。但又多一套語法可以寫錯。 |
| **錨點** | 一個起點標記加一個終點標記。 | 檔案位移也不怕。但標記重複時會有歧義。 |

Claude Code 用的是精確的舊字串替換，而且逼模型先讀過檔案，所以字串一過期就直接報錯，不會改錯行。
書裡描述 Cursor 改送一份粗略的骨架，再由第二個訓練過的 model 依它把檔案重寫一遍，並說這條路比較快。

**提早啟動與失敗範圍。**能重疊的不只是批次。一個呼叫只要自己的參數解析完就可以先跑，這時模型還在寫同一批的其他呼叫。
這樣就把這個呼叫的延遲藏進生成裡了。它需要一條失敗規則：出錯只停掉依賴它的那些呼叫。
同一批裡互不相干的呼叫照跑，外面那個 turn 也照跑。

**shell 狀態。**兩種設計，都站得住腳。

- **每次呼叫都重置：**Claude Code 的 bash 工具不會在呼叫之間留著一個活的 shell。這次設的環境變數和 shell function，下一次就沒了，
  工具描述也直接叫模型用絕對路徑。每個呼叫自己就重現得出來，平行呼叫之間也不會互相污染。
- **共用一個常駐 session：**書裡把共用一個終端機當成預設。`cd`、export 出去的變數、啟用中的虛擬環境，全都留得住。
  要平行做事時，另外開幾個隔離的 shell 就好。模型少打很多重複的設定指令，harness 則多了一份 session 狀態要追蹤和重置。

**大目錄的探索。**目錄一大就不可能整份送出去，所以 registry 先送名稱，等有人要了才載入完整的 schema。
提出需求的可以是模型自己，用白話講就行。MCP-Zero 讓 agent 說出自己缺哪一種能力，先配對到 server，再配對到那台 server 上的工具，最後只注入配到的那份 schema。
模型從頭到尾都不必知道那個工具存在，這是關鍵字搜尋做不到的。

**對 cache 友善的載入。**schema 放在哪裡有差。附在 context 最後面一次，然後就別再動它。
去改 prompt 前面那塊工具定義，會讓快取住的前綴連同後面每一個 token 一起失效（第 10 章）。
用附加的，前綴不受影響，那份 schema 到下一輪就變成普通的歷史紀錄。

---

## 各系統做法

各個 agent 如何定義工具、路由呼叫、處理平行，以及公開一份龐大目錄。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 每個工具各自帶驗證、權限、安全平行和延遲探索。 | 單一 `bash` 工具小得多，也沒有目錄要維護。 |
| **Cons** | 每個工具都得背一份契約。 | 驗證和權限做不到 per-tool。跑指令前的確認（第 3 章）看到的只有一條指令字串。 |
| **Why** | 新增一項能力，應該就只是註冊一個工具，loop 維持不變。 | 假設每個行動都能寫成一條 shell 指令，所以一個工具就夠了。 |
| **How: tool definition** | schema、handler 與判定式。 | 一份寫死的 `bash` schema 就是整份型錄，只有一個指令欄位，別的名稱一律報錯。 |
| **How: dispatch** | 依名稱查表，含別名。工具池依權限篩選，並合併 MCP 工具。 | 沒有 registry，每次呼叫都是一條 shell 指令。 |
| **How: parallel calls** | 安全呼叫批次執行，不安全的單獨執行。安全標記預設關閉。 | 沒有。舊版文字模式每次回應只允許一個 action。 |
| **How: discovery** | 先給名稱。完整 schema 依精確名稱或關鍵字隨需載入。 | 只有一個工具，不需要。 |

---

## 哪裡會出錯

- **未知的工具名稱：**模型指名了一個不存在或已停用的工具。回傳一個 `tool_result` 錯誤，而不是讓 loop 崩潰。
- **schema 漂移：**schema 說一套，handler 期待另一套。在 dispatch 前先驗證。
- **不安全的平行：**兩個寫入可能損毀同一個檔案。預設採依序執行，除非確知某工具是安全的。
- **目錄 overflow：**太多工具 schema 會擠爆 prompt。把完整 schema 延後到需要時再給，載入時附在最後面，讓快取住的前綴不受影響。
- **結果過大：**龐大的輸出可能塞滿 context window。限制結果大小、保存完整輸出，並回傳一段預覽加一個路徑。
  截斷要標出來。默默截掉，模型就會把一份殘缺的檔案當成完整的在讀。
- **挑錯工具：**兩份 description 重疊，或一個工具身兼兩職。把重複的合併、把過載的 schema 拆開，並在每份 description 裡講明這個工具不做什麼。
- **input 被偷偷改掉：**harness 在送進 handler 的路上做了正規化，或多塞了一個參數。呼叫失敗了，模型卻查不出原因。輸入不合法就帶著理由拒絕。
- **失敗擴散整批：**平行批次裡有一個呼叫失敗，整個 turn 就跟著死。只中止依賴它的那些呼叫。

---

## 可執行程式

[`src/`](src/) 承接 01 往前走，並加上：

- [`tools.py`](src/tools.py)：`Tool`、`Registry` 與 `run_concurrently`。
- [`loop.py`](src/loop.py)：把每個 `tool_use` 透過 `Registry` dispatch。
- [`demo.py`](src/demo.py)：註冊一個 `ReadFile` 工具，並對著 API 執行 loop。
- [`test.py`](src/test.py)：檢查 dispatch、未知工具錯誤與平行批次。

```bash
python sections/02-tool-runtime/src/test.py         # offline checks, no key
uv run python sections/02-tool-runtime/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code)：
  `Tool.ts`、`tools.ts`、`services/tools/toolOrchestration.ts`、`services/tools/toolExecution.ts`、`tools/ToolSearchTool/ToolSearchTool.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`models/utils/actions_toolcall.py`、`models/utils/actions_text.py`、`environments/__init__.py`。
- [learn-claude-code · s02_tool_use](https://github.com/shareAI-lab/learn-claude-code)：章節框架。
- [ai-agent-book](https://github.com/bojieli/ai-agent-book)：`book/chapter4.md`、`book/chapter5.md`（《深入理解 AI Agent》，李博杰；以中文原版為準）：
  五類工具的分法、粒度、description 的寫法、參數保真、感知工具的介面規則、主動探索、對 cache 友善的載入、
  串流式提早啟動與只中止依賴項、常駐 shell 預設、搜尋與編輯的比較，以及檢查用參數。
  書中對 Claude Code 和 Cursor 的判讀來自作者自己讀原始碼，而那些實作變動很快，當成當時的證據看就好。
- [MCP-Zero](https://arxiv.org/abs/2506.01056)（Fei 等人）：agent 自己說出缺哪種能力，配對先找 server、再找工具。
- [τ-bench](https://arxiv.org/abs/2406.12045)（Sierra）：成績看資料庫的終態，檢查用參數靠的就是這個。
