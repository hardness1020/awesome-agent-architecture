# 10 · System prompt assembly

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 每一輪都從即時狀態組出 prompt。

system prompt 是 agent 的常駐指令集。它描述身分、規則、工具、專案脈絡，以及啟用中的功能。

在真實的 agent 裡，這不能只是一個寫死的字串。

工具、記憶、輸出風格、MCP 伺服器和各種模式會因 session 而異。prompt 應該描述實際啟用中的內容。

一個 prompt 組裝器解決三個問題：

1. 新功能的文字有明確的落腳處。
2. 沒啟用的功能文字可以被略過。
3. 穩定的段落可以使用 prompt caching。

沒有組裝，prompt 會變得過時、臃腫，或難以安全地修改。

---

## 機制

把 prompt 定義成一組具名的段落。有些段落是靜態的。有些會從即時狀態計算文字，在不適用時回傳 `None`。

組裝很簡單：解析每個段落，丟掉 `None`，把其餘的接起來。

```python
sections = [
    intro, system_rules, doing_tasks, tools_section,
    session_guidance(), memory(), env_info(),
    output_style(), mcp_instructions(),
]
prompt = [s for s in resolve(sections) if s is not None]
```

兩條規則讓它保持可控：

1. 依狀態納入段落，不要靠關鍵字猜測。
2. 讓易變的內容遠離穩定的 prompt 前綴。

### New: sections and assemble

```python
@dataclass
class Section:                                          # src/prompt.py
    name: str
    compute: Callable    # (state) -> str | None ; static sections ignore state

def static(name, text) -> Section:
    return Section(name, lambda _state: text)

def assemble(sections, state) -> str:                  # the prompt for this turn
    parts = (s.compute(state) for s in sections)
    return "\n\n".join(p for p in parts if p is not None)
```

段落清單本身負責由狀態驅動的納入：

```python
DEMO_SECTIONS = [
    static("intro", "You are a tiny agent. ..."),
    Section("tools", lambda s: "Tools: " + ", ".join(s["tools"]) if s.get("tools") else None),
    Section("env", lambda s: f"cwd: {s['cwd']}" if s.get("cwd") else None),
    Section("mcp", lambda s: "MCP servers connected; ..." if s.get("mcp") else None),
]
```

回想出的記憶不屬於這個 prompt。它由第 9 章以一則 `<system-reminder>` 訊息注入。這讓 prompt 前綴更穩定。

### How it integrates

迴圈在每次模型呼叫前組出 prompt：

```python
for _ in range(max_steps):                             # src/loop.py
    messages = context.manage(messages, summarizer=summarizer)
    system = prompt(registry, session) if prompt else None   # 10 · assemble from live state
    response = model(messages, registry, system)
    ...
```

- `prompt` 是一個閉包住段落清單的可呼叫物件。
- 它讀取即時狀態，例如啟用中的工具和 session 模式。
- 傳入 `prompt=None` 會維持第 9 章的行為。

### Prompt caching

大多數 system prompt 段落在一次 session 中是穩定的。demo 設了一個頂層的 cache 斷點：

```python
client.messages.create(model=MODEL, system=assemble(DEMO_SECTIONS, state),
                       messages=messages, cache_control={"type": "ephemeral"})
```

穩定的內容應該排在易變的內容之前。如果一個會變動的值出現在前面，它可能會讓更多快取失效。

Claude Code 也使用一個明確的動態邊界。當較小的動態尾段變動時，這能保護一大段靜態前綴。

---

## 各系統做法

每一輪如何組出 prompt。

| System | Assembly point | Sections | When built |
| --- | --- | --- | --- |
| **Claude Code** | `getSystemPrompt()`。 | 靜態與動態段落。 | 每一輪從即時狀態組出。 |

### Claude Code

- `getSystemPrompt()` 回傳一個 `string[]`，每個段落一個元素。
- 工具指引由啟用中的工具集組出。
- 動態段落會被記憶（memoize），直到 `/clear` 或 `/compact`。
- MCP 指令不使用快取，因為伺服器可能改變。
- CLAUDE.md、日期和 git 狀態以 context 訊息注入，而不是 prompt 段落。
- `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 把穩定前綴和會變動的尾段分開。

> **取捨：** 以段落為基礎的組裝避免了過時或不相關的指令。它多了一份段落 registry、快取失效規則，以及排序上的紀律。

---

## 失效模式

- **易變文字打壞快取：**把會變動的內容放到後面，或放到 prompt 前綴之外。
- **段落快取過時：**當 session 狀態改變時，清掉被記憶的段落。
- **Prompt 提到不存在的工具：**從即時啟用的工具集生成工具文字。
- **脈絡混進 prompt：**當專案檔案、日期和 git 狀態經常變動時，把它們放進 context 訊息。
- **Prompt 覆寫互相衝突：**用單一 resolver 定義優先順序。

---

## 可執行程式

[`src/`](src/) 承接 09 並加入：

- [`prompt.py`](src/prompt.py)：`Section`、`static` 和 `assemble`。
- [`loop.py`](src/loop.py)：每一輪重新組出 prompt。
- [`demo.py`](src/demo.py)：加入頂層的 `cache_control`。
- [`test.py`](src/test.py)：檢查由狀態驅動的納入。

```bash
python sections/10-system-prompt/src/test.py         # offline checks, no key
uv run python sections/10-system-prompt/src/demo.py  # live demo, needs a key
```

---

## 出處

- Claude Code 原始碼：`constants/prompts.ts`、`constants/systemPromptSections.ts`、`utils/api.ts`、`QueryEngine.ts`。
- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)：cache 斷點、TTL、定價，以及 token 下限。
- learn-claude-code · s10_system_prompt：章節框架。
