# 3 · Permission & sandbox

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 在每個動作抵達系統之前先做檢查。

模型可以要求執行任何已啟用的工具。permission 層負責決定該次呼叫是否可以執行。

一個沒有 permission 的工具執行環境，幾乎等同於一個無人看管的遠端 shell。

一次錯誤的工具呼叫可能刪除檔案、洩漏機密，或推送錯誤的程式碼。信任模型不是一道安全邊界。程式必須在執行前檢查請求。

permission 層必須做到：

1. 在每個工具呼叫執行前先檢視它。
2. 決定 `allow`、`ask` 或 `deny`。
3. 當高風險的呼叫尚未預先核准時，詢問人類。
4. 當呼叫真的執行時，限制它造成的損害。

沒有這一層，一次錯誤的工具呼叫就可能造成無法回復的副作用。

---

## 機制

一個純函式負責做出 permission 決策。它讀取工具、目前的 mode，以及所有的 allow 規則，並回傳三個值之一：

- `allow`：執行工具。
- `ask`：暫停並詢問人類。
- `deny`：不執行工具。

mode 會改變預設行為。舉例來說，plan mode 允許唯讀工具，但在計畫核准前拒絕編輯。

### New: the gate

`decide()` 就是整個 permission 決策：

```python
def decide(tool, mode, allow_rules) -> str:      # src/permissions.py (new)
    if mode == BYPASS:                            # operator opted out
        return "allow"
    if mode == PLAN:                              # exploring, not acting yet
        if tool.is_read_only:           return "allow"
        if tool.name == "ExitPlanMode": return "ask"     # approval handshake (section 5)
        return "deny"                             # no side effects until approved
    if tool.is_read_only or tool.name in allow_rules:
        return "allow"
    if mode == ACCEPT_EDITS and tool.is_edit:
        return "allow"                            # a class of work pre-approved
    return "ask"                                  # default: when unsure, ask
```

這個函式沒有 I/O。這讓它可以一個 mode 一個 mode 地輕鬆測試。

### How it integrates

gate 在 `_dispatch` 內部執行，就在 `run_tool` 之前：

```python
def _dispatch(block, registry, mode, allow_rules, approver):   # src/loop.py
    ...                                                  # resolve tool (section 2)
    decision = decide(tool, mode, allow_rules)           # 3 · the gate, the new line
    if decision == "deny":
        return res(f"{name} not allowed in {mode} mode")
    if decision == "ask" and not approver(name, block.input):
        return res(f"{name} denied by user")
    return res(run_tool(tool, block.input))              # only now does it run
```

- 迴圈主體和第 1、2 章相同，沒有改變。
- 只有 `_dispatch` 多了 gate。
- `deny` 以及未核准的 `ask` 永遠不會抵達 `run_tool`。
- 拒絕結果仍會以 `tool_result` 回傳，所以模型看得到發生了什麼，並能隨之調整。
- `approver` 預設為 `False`，所以 `ask` 代表「否」，除非人類核准。

關鍵不變條件維持不變：每個工具呼叫都會產生一則結果訊息，即使真正的動作沒有執行。

真實系統會加上規則優先序、記住的核准，以及沙箱化的執行。這些都是同一個 gate 的延伸。

---

## 各系統做法

各個 agent 如何管制副作用、切換 mode，以及記住決策。

| System | Gate point | Permission modes | Sandbox | Rule persistence |
| --- | --- | --- | --- | --- |
| **Claude Code** | 每個工具執行前。 | Default、edit-approved、plan、deny 與 bypass 等 mode。 | Bash 可以在沙箱內執行。 | 規則可存在 session 或 settings 中。 |

### Claude Code

- `QueryEngine.ts` 對每次工具使用呼叫 `canUseTool`。
- `useCanUseTool.tsx` 解析出一個 `PermissionDecision`：`allow`、`deny` 或 `ask`。
- 對外的 mode 包含 `default`、`acceptEdits`、`plan`、`bypassPermissions` 與 `dontAsk`。
- 內部的 mode 包含 `auto` 與 `bubble`。
- 規則會依優先序，從 user、project、local、flag、policy、CLI、command 與 session 等來源合併。
- 核准可以透過 `PermissionUpdate.ts` 存到 session 或 settings。
- `Bash` 使用 `shouldUseSandbox.ts` 與 `SandboxManager`。
- `WebFetch` 對選定的文件主機有一份獨立的預先核准清單。
- MCP server 與遠端執行有各自的核准路徑。

> **取捨：** mode、有序規則與沙箱化提供了精確的控制，但也帶來許多需要推敲的狀態。每一條 bypass 或預先核准的路徑都必須保持可見且範圍狹窄。

---

## 失效模式

- **Pattern-match bypass：**字串式的 deny 清單會漏掉 shell 的各種變體。優先採用行為檢查與沙箱化，而不是原始的子字串比對。
- **Mode 開得太寬：**一條範圍過大的 allow 規則或 bypass mode，可能讓後續的高風險呼叫悄悄執行。限縮 bypass 的範圍，並讓目前的 mode 顯示出來。
- **核准疲勞：**每次呼叫都詢問，會訓練使用者不看內容就核准。預先核准低風險的類別，但讓破壞性動作維持明確詢問。
- **subagent 內的無聲拒絕：**子 agent 可能沒有終端機可以詢問。應把提示往上轉給父 agent 代問，而不是無聲失敗。
- **沙箱被停用：**若一個被允許的指令在沙箱外執行，permission 提示就是最後一道檢查。任何未沙箱化的路徑都要用政策擋在後面。

---

## 可執行程式

[`src/`](src/) 承接 02 並加上：

- [`permissions.py`](src/permissions.py)：涵蓋四種 mode 的 `decide`。
- [`loop.py`](src/loop.py)：在 `_dispatch` 中於執行前管制每個呼叫。

```bash
python sections/03-permission-sandbox/src/test.py         # offline checks, no key
uv run python sections/03-permission-sandbox/src/demo.py  # live demo, needs a key
```

---

## 出處

- Claude Code 原始碼：`QueryEngine.ts`、`hooks/useCanUseTool.tsx`、`types/permissions.ts`、`utils/permissions/PermissionUpdate.ts`。
- Claude Code 沙箱與 web gate：`tools/BashTool/shouldUseSandbox.ts`、`tools/WebFetchTool/preapproved.ts`。
- learn-claude-code · s03_permission：section framing。
