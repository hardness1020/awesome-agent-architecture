# 2 · Tool runtime

[English](README.md) · **繁體中文**

> 新增一項能力，就是註冊一個工具。迴圈維持不變。

agent 迴圈只能透過工具來行動。模型會發出一個結構化的 `tool_use` 區塊，帶有 `name` 與 `input`。

harness 把那個名稱對應到程式碼。它驗證輸入、執行 handler，並回傳結果。

這個 runtime 必須：

1. 告訴模型有哪些工具存在。
2. 描述每個工具的 input schema。
3. 依名稱把每個 `tool_use` 路由出去。
4. 在可行時平行執行安全的呼叫。
5. 讓龐大的工具目錄仍可被探索。

沒有這一層，模型能要求行動，卻沒有東西能真正執行那個行動。

如果只有一個 `bash` 工具，每一項能力都變成字串處理。沒有各別工具的驗證或權限邏輯。

---

## 機制

一個工具是一個小物件，帶有名稱、handler、schema 與幾個判定式。registry 依名稱存放工具。dispatch 就是一次查表。

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

第 1 章用的是內嵌的 `HANDLERS` dict。第 2 章把一個 `registry` 傳進迴圈，並把每個 `tool_use` 透過 `_dispatch` 路由：

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

迴圈主體其餘部分維持不變。只有 dispatch 這一步現在改用 registry。

`_dispatch` 是下一個延伸點。第 3 章在那裡加上權限關卡。第 4 章在那裡加上 hook。

demo 為了清楚起見採依序 dispatch。真實的 runtime 會把安全呼叫批次化，並隨需載入龐大的工具 schema。

---

## 各系統做法

各個 agent 如何定義工具、路由呼叫、處理平行，以及公開一份龐大目錄。

| System | 工具定義 | Dispatch | 平行呼叫 | 探索 |
| --- | --- | --- | --- | --- |
| **Claude Code** | schema、handler 與判定式。 | 依名稱查表，含別名。 | 安全呼叫批次執行。不安全呼叫依序執行。 | 先給名稱。schema 於請求時提供。 |

### Claude Code

- `buildTool` 設定安全的預設值。`isConcurrencySafe` 與 `isReadOnly` 預設為 `false`。
- `getAllBaseTools()` 列出內建工具，例如 `BashTool`、`FileReadTool`、`FileEditTool`、`GrepTool` 與 `AgentTool`。
- `getTools()` 與 `assembleToolPool()` 依權限篩選工具，並合併 MCP 工具。
- `findToolByName` 依 `name` 與 `aliases` 解析。
- `partitionToolCalls` 把 concurrency-safe 的呼叫分組，透過 `runToolsConcurrently` 執行。
- 不安全的呼叫會打斷批次，單獨執行。
- 標記為 `shouldDefer` 的工具先以名稱出貨。`ToolSearchTool` 依精確名稱或關鍵字載入完整 schema。

> **取捨：** 每個工具一個物件模型，帶來驗證、權限、安全的平行，以及延遲探索。
> 它同時也讓每個工具都要背負一份契約。
> 單一 `bash` 工具比較小，但它無法分別驗證輸入或把關行動。

---

## 失效模式

- **未知的工具名稱。** 模型指名了一個不存在或已停用的工具。回傳一個 `tool_result` 錯誤，而不是讓迴圈崩潰。
- **schema 漂移。** schema 說一套，handler 期待另一套。在 dispatch 前先驗證。
- **不安全的平行。** 兩個寫入可能損毀同一個檔案。預設採依序執行，除非確知某工具是安全的。
- **目錄溢位。** 太多工具 schema 會擠爆 prompt。把完整 schema 延後到需要時再給。
- **結果過大。** 龐大的輸出可能塞滿 context window。限制結果大小、保存完整輸出，並回傳一段預覽加一個路徑。

---

## 可執行程式

[`src/`](src/) 承接 01 往前走，並加上：

- [`tools.py`](src/tools.py)：`Tool`、`Registry` 與 `run_concurrently`。
- [`loop.py`](src/loop.py)：把每個 `tool_use` 透過 `Registry` dispatch。
- [`demo.py`](src/demo.py)：註冊一個 `ReadFile` 工具，並對著 API 執行迴圈。
- [`test.py`](src/test.py)：檢查 dispatch、未知工具錯誤與平行批次。

```bash
python sections/02-tool-runtime/src/test.py         # offline checks, no key
uv run python sections/02-tool-runtime/src/demo.py  # live demo, needs a key
```

---

## 出處

- Claude Code source：`Tool.ts`、`tools.ts`、`services/tools/toolOrchestration.ts`、`services/tools/toolExecution.ts`、`tools/ToolSearchTool/ToolSearchTool.ts`。
- learn-claude-code · s02_tool_use：章節框架。
