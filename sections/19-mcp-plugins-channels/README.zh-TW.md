# 19 · MCP / plugins / channels

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 能力不夠？插進更多。harness 靠一套標準 protocol 接上外面的世界。

一個 harness（外層架構）只能做它的工具允許它做的事，而每個內建工具都是預先定義好的：input schema、執行邏輯、錯誤處理，全都是。

這無法擴展到使用者想要的各種服務：issue tracker、部署系統、知識庫。你沒辦法為每一個服務、用它各自的語言，都寫一個專屬工具。

MCP（Model Context Protocol）就是填補這道缺口的開放標準。一個外部服務宣告它的工具，agent 則盲呼叫它們，不需要知道是誰寫的、怎麼寫的。

於是 agent 不需要任何人動 harness，就得到了 Jira 工具或部署工具。少了 MCP，agent 的能力就停在安裝當下內建的那一套，之後加不了新的。

MCP 之外，這一章還講兩個搭在它上面的機制：plugin 把 server 跟 hook、skill 打包在一起，讓人一次裝好；channel 則讓 server 能主動把訊息推回來。兩者都跑在同一套 protocol 上。

---

## 機制

![機制圖](assets/19-mcp-plugins-channels.png)

連上每個 server，探索它的工具（`tools/list`），把每個工具包裝成一個 runtime `Tool`（第 2 章），再把這些合併進 loop 用來 dispatch 的同一個工具池。

名稱以 `mcp__<server>__<tool>` 加上命名空間，所以兩個 server 永遠不會撞名。loop 與 gate 都不變：一個 MCP 工具就是一個 `Tool`，只是它的 `run()` 會透過 transport 對外呼叫。

- 對每個 server 呼叫一次 `tools/list`，問它有哪些工具；回傳清單裡的每一筆規格，都被包成一個 `Tool`。
- 名稱加了命名空間並經過正規化，所以它是唯一的，也符合 API 的名稱樣式。
- 每個工具的 MCP annotation（`readOnlyHint`、`destructiveHint`）成為 gate 讀取的權限提示（第 3 章）。
- 合併進那一個 `Registry` 之後，模型會在同一份清單裡看到 MCP 工具與內建工具。

### New: 包裝探索到的工具

`mcp.py` 把每個探索到的規格變成一個 `Tool`。名稱加上命名空間讓 server 永不撞名，並正規化到符合 API 的字元集：

```python
def tool_name(server, tool):                           # src/mcp.py
    return f"mcp__{normalize(server)}__{normalize(tool)}"   # buildMcpToolName

def wrap(server, spec, call):
    ann = spec.get("annotations", {})
    read_only = bool(ann.get("readOnlyHint"))
    bare = spec["name"]
    return Tool(
        name=tool_name(server, bare),
        run=lambda args, _t=bare: call(_t, args),      # dispatch calls out over the transport
        input_schema=spec.get("inputSchema") or dict(NO_INPUT),
        is_read_only=read_only,
        is_concurrency_safe=read_only,                 # reads are safe to batch
    )
```

- `tool_name` 為每個工具加上命名空間；`normalize` 把任何落在 `[a-zA-Z0-9_-]` 之外的字元換成 `_`，以符合 API 名稱樣式。
- `run` 捕捉了裸工具名與 server 的 `call`，所以 dispatch 被包裝的 `Tool` 時會透過 transport 回呼過去。
- `readOnlyHint` annotation 成為 `is_read_only`，這正是權限 gate（第 3 章）用來決定放行或詢問的依據。

### New: 探索與合併

`connect` 執行一次探索並回傳被包裝的工具；呼叫端把它們合併進 loop 的 `Registry`：

```python
def connect(server, conn):                             # src/mcp.py
    return [wrap(server, spec, conn.call) for spec in conn.list_tools()]
```

- `conn` 是一個活的 transport：正式環境是 `stdio` 或 `http`，demo 裡是 in-process。探索並不在意是哪一種。
- 回傳的 `Tool` 註冊進與內建工具同一個池，所以 `registry.schemas()` 會把它們一起公告，loop 也以相同方式 dispatch。

### New: channel 與 plugin 設定

這一章還剩兩個小機制。

第一個是反向的訊息流：平常是 agent 去呼叫 server，但 server 也可以主動把訊息推進來，例如一則 Slack 訊息到了。harness 把這段文字包上 `<channel>` 標籤，接在 agent 下一輪輸入的前面，模型就會讀到它：

```python
def wrap_channel(source, payload):                     # src/mcp.py
    return f'<{CHANNEL_TAG} source="{source}">{payload}</{CHANNEL_TAG}>'
```

第二個是設定的疊加：同一個 server 可能同時出現在 plugin、使用者和專案的設定裡，`merge_servers` 依優先序決定誰生效：

```python
def merge_servers(*layers):                            # src/mcp.py
    merged = {}
    for scope in PRECEDENCE:                            # plugin < user < project < local
        for layer in layers:
            merged.update(layer.get(scope, {}))
    return merged
```

- `wrap_channel` 把 Slack、Discord 或 SMS 變成同一套 protocol 上的雙向介面；帶標籤的區塊像一則背景備註一樣進入佇列（第 13 章）。
- `merge_servers` 解決一個在多個 scope 都有定義的 server：`local` 覆蓋 `project`，`project` 覆蓋 `user`，`user` 覆蓋 `plugin`。

channel 的訊息誰都能發：從 Slack 或 SMS 進來的文字不一定出自使用者本人，可能是垃圾訊息，甚至是想操縱 agent 的指令。所以訊息得先通過 gate 檢查，才能變成一個 turn（Hermes 對每則進來的訊息，在 auth 之前就 fire `pre_gateway_dispatch`）：

```python
def gate_inbound(source, payload, gates=()):           # src/mcp.py
    for gate in gates:
        out = gate(source, payload) or {}
        if out.get("drop"):
            return None                                # discarded: the model never reads it
        if out.get("rewrite") is not None:
            payload = out["rewrite"]                   # e.g. redact a secret
    return wrap_channel(source, payload)
```

- 一個 gate 可以 drop（垃圾訊息、不明寄件者）或 rewrite（遮蔽機密），發生在 loop 看到文字之前。
- 回傳 `None` 代表這則訊息不會變成任何 turn，垃圾輸入連一次模型呼叫都不用花。

### 如何整合

demo 探索一個 server 並跑一輪 agent。模型盲呼叫這個 MCP 工具：

```python
reg = Registry()
for t in mcp.connect("kb", KBServer()):                # discover, wrap, merge
    reg.register(t)
run_turn([...goal...], model, reg, Session(mode=DEFAULT))   # the one agent call
```

- 模型在它的工具清單裡看到 `mcp__kb__search` 就在任何內建工具旁邊，並呼叫它；它永遠不會得知是誰寫了這個工具。
- 這個工具是唯讀的，所以 gate 不提示就放行。一個具破壞性的工具則會詢問，或由一條以完整名稱為鍵的規則預先核准。
- loop 不變。MCP 只是往池裡加工具；下游的一切都是第 2 章的 dispatch 與第 3 章的 gating。

---

## 各系統做法

harness 如何伸手觸及自身之外。

| | Claude Code | Hermes Agent |
| --- | --- | --- |
| **Pros** | 任何服務、任何語言都接得上，不用改 harness。loop 與 gate 都不變。 | 其他 client 能把它當 MCP server 來用。每則從平台進來的訊息都先過 gate。 |
| **Cons** | 每個連上的 server 都是新的攻擊面，annotation 又是自我陳報的。工具清單會膨脹。 | channel 的訊息誰都能發：垃圾訊息、想操縱 agent 的指令也會進來。 |
| **Why** | 少了 MCP，能力就停在安裝當下內建的那一套。 | agent 同時是 MCP client 和 MCP server，聊天平台就是它的雙向介面。 |
| **How: transports** | 六種，從 stdio 到 http/sse/ws。本地與遠端 server 各連各的池。 | MCP 雙向，加上聊天平台 adapter。語音走同樣的 channel。 |
| **How: plugin format** | 一個 plugin 打包 server、hook、skill。設定按優先序分層合併。 | 一份 manifest 加一個註冊進入點。要覆蓋內建工具，操作者得明確同意。 |
| **How: tool pool assembly** | 每個 server 工具被複製、加命名空間，並與內建工具合併。annotation 成為 gate 的權限提示。 | plugin 與 MCP 工具加入同一個 import 時建立的 registry。 |

---

## 哪裡會出錯

- **撞名（Name collisions）：**兩個 server 都公開 `search`。`mcp__server__tool` 命名空間避免了衝突；但一個名稱含 `__` 的 server 仍會被解析錯誤，所以名稱要保持簡單。
- **工具清單膨脹（Tool-list bloat）：**太多 server 會造成龐大的工具清單，既花 token 又干擾選擇（第 2 章）。緩解：截斷描述並延後載入。
- **connect 之後池過時：**一個在 session 中途加入的 server 不在 cache 的工具清單裡，於是模型永遠看不到它。緩解：變動時重建池並重建 prompt（第 8 章）。
- **連線抖動（Connection churn）：**一個不穩的 server 會逾時、重置，或 token 過期。緩解：反覆失敗後重連、`401` 時重新驗證、為每次呼叫設逾時（第 11 章）。
- **被過度信任的副作用：**一個 server 把具破壞性的工具標成 `readOnlyHint: true` 以跳過提示。緩解：以完整名稱設一條規則照樣 gate 它（第 3 章）。

---

## 可執行程式

[`src/`](src/) 承接第 18 章並加上：

- [`mcp.py`](src/mcp.py)：探索與包裝、plugin 設定合併、channel 包裝，以及入站 gate（`gate_inbound`）。
- [`test.py`](src/test.py)：探索與命名空間、權限提示的對應、連同 gate 合併進池、設定優先序、channel 標籤，以及入站的 drop 與 rewrite。
- [`demo.py`](src/demo.py)：一輪 agent 透過探索到的 `mcp__kb__search` 盲呼叫一個 in-process MCP 工具。

loop 與 dispatch 都不變。MCP 只是往第 2 章的池裡加工具；第 3 章的 gate 讀取它們自我宣告的 annotation。

```bash
python sections/19-mcp-plugins-channels/src/test.py         # offline checks, no key
uv run python sections/19-mcp-plugins-channels/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code MCP transport](https://github.com/yasasbanukaofficial/claude-code)：`services/mcp/types.ts`（`TransportSchema`）、`client.ts`（`MCPTool` cloning、`buildMcpToolName`）、`normalization.ts`（`normalizeNameForMCP`）。
- [Claude Code MCP config and channels](https://github.com/yasasbanukaofficial/claude-code)：`config.ts`（precedence）、`channelNotification.ts`（`CHANNEL_TAG`），加上 `McpAuthTool`、`ListMcpResourcesTool`、`ReadMcpResourceTool`。
- [Claude Code plugins](https://github.com/yasasbanukaofficial/claude-code)：`plugins/builtinPlugins.ts`、`plugins/bundled/`、`types/plugin.ts`，加上 `remote/` 與 `bridge/`。
- [Hermes Agent 原始碼](https://github.com/NousResearch/hermes-agent)：`mcp_serve.py`、`hermes_cli/plugins.py`（`PluginManager`、`VALID_HOOKS`）、`gateway/platforms/`、`gateway/platform_registry.py`、`plugins/platforms/`。
- 章節定位：[learn-claude-code · s19_mcp_plugin](https://github.com/shareAI-lab/learn-claude-code)。
