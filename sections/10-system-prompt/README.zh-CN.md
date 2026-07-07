# 10 · System prompt assembly

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 每一轮都从实时状态组出 prompt。

system prompt 是 agent 的常驻指令集。它描述身份、规则、工具、项目上下文，以及启用中的功能。

在真实的 agent 里，这不能只是一个写死的字符串。

工具、记忆、输出风格、MCP 服务器和各种模式会因 session 而异。prompt 应该描述实际启用中的内容。

一个 prompt 组装器解决三个问题：

1. 新功能的文字有明确的落脚处。
2. 没启用的功能文字可以被略过。
3. 稳定的段落可以使用 prompt caching。

没有组装，prompt 会变得过时、臃肿，或难以安全地修改。

---

## 机制

把 prompt 定义成一组具名的段落。有些段落是静态的。有些会从实时状态计算文字，在不适用时返回 `None`。

组装很简单：解析每个段落，丢掉 `None`，把其余的接起来。

```python
sections = [
    intro, system_rules, doing_tasks, tools_section,
    session_guidance(), memory(), env_info(),
    output_style(), mcp_instructions(),
]
prompt = [s for s in resolve(sections) if s is not None]
```

两条规则让它保持可控：

1. 依状态纳入段落，不要靠关键字猜测。
2. 让易变的内容远离稳定的 prompt 前缀。

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

段落列表本身负责由状态驱动的纳入：

```python
DEMO_SECTIONS = [
    static("intro", "You are a tiny agent. ..."),
    Section("tools", lambda s: "Tools: " + ", ".join(s["tools"]) if s.get("tools") else None),
    Section("env", lambda s: f"cwd: {s['cwd']}" if s.get("cwd") else None),
    Section("mcp", lambda s: "MCP servers connected; ..." if s.get("mcp") else None),
]
```

回想出的记忆不属于这个 prompt。它由第 9 章以一条 `<system-reminder>` 消息注入。这让 prompt 前缀更稳定。

### How it integrates

循环在每次模型调用前组出 prompt：

```python
for _ in range(max_steps):                             # src/loop.py
    messages = context.manage(messages, summarizer=summarizer)
    system = prompt(registry, session) if prompt else None   # 10 · assemble from live state
    response = model(messages, registry, system)
    ...
```

- `prompt` 是一个闭包住段落列表的可调用对象。
- 它读取实时状态，例如启用中的工具和 session 模式。
- 传入 `prompt=None` 会维持第 9 章的行为。

### Prompt caching

大多数 system prompt 段落在一次 session 中是稳定的。demo 设了一个顶层的 cache 断点：

```python
client.messages.create(model=MODEL, system=assemble(DEMO_SECTIONS, state),
                       messages=messages, cache_control={"type": "ephemeral"})
```

稳定的内容应该排在易变的内容之前。如果一个会变动的值出现在前面，它可能会让更多缓存失效。

Claude Code 也使用一个明确的动态边界。当较小的动态尾段变动时，这能保护一大段静态前缀。

---

## 各系统做法

每一轮如何组出 prompt。

| System | Assembly point | Sections | When built |
| --- | --- | --- | --- |
| **Claude Code** | `getSystemPrompt()`。 | 静态与动态段落。 | 每一轮从实时状态组出。 |

### Claude Code

- `getSystemPrompt()` 返回一个 `string[]`，每个段落一个元素。
- 工具指引由启用中的工具集组出。
- 动态段落会被记忆（memoize），直到 `/clear` 或 `/compact`。
- MCP 指令不使用缓存，因为服务器可能改变。
- CLAUDE.md、日期和 git 状态以 context 消息注入，而不是 prompt 段落。
- `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 把稳定前缀和会变动的尾段分开。

> **取舍：** 以段落为基础的组装避免了过时或不相关的指令。它多了一份段落 registry、缓存失效规则，以及排序上的纪律。

---

## 失效模式

- **易变文字打坏缓存：**把会变动的内容放到后面，或放到 prompt 前缀之外。
- **段落缓存过时：**当 session 状态改变时，清掉被记忆的段落。
- **Prompt 提到不存在的工具：**从实时启用的工具集生成工具文字。
- **上下文混进 prompt：**当项目文件、日期和 git 状态经常变动时，把它们放进 context 消息。
- **Prompt 覆盖互相冲突：**用单一 resolver 定义优先顺序。

---

## 可执行程序

[`src/`](src/) 承接 09 并加入：

- [`prompt.py`](src/prompt.py)：`Section`、`static` 和 `assemble`。
- [`loop.py`](src/loop.py)：每一轮重新组出 prompt。
- [`demo.py`](src/demo.py)：加入顶层的 `cache_control`。
- [`test.py`](src/test.py)：检查由状态驱动的纳入。

```bash
python sections/10-system-prompt/src/test.py         # offline checks, no key
uv run python sections/10-system-prompt/src/demo.py  # live demo, needs a key
```

---

## 来源

- Claude Code 源码：`constants/prompts.ts`、`constants/systemPromptSections.ts`、`utils/api.ts`、`QueryEngine.ts`。
- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)：cache 断点、TTL、定价，以及 token 下限。
- learn-claude-code · s10_system_prompt：章节框架。
