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

![机制图](assets/10-system-prompt-assembly.png)

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

### New: 段落与组装

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

每个段落要不要出现在 prompt 里，是它自己看状态决定的。`compute` 返回 `None` 就略过：

```python
DEMO_SECTIONS = [
    static("intro", "You are a tiny agent. ..."),
    Section("tools", lambda s: "Tools: " + ", ".join(s["tools"]) if s.get("tools") else None),
    Section("env", lambda s: f"cwd: {s['cwd']}" if s.get("cwd") else None),
    Section("mcp", lambda s: "MCP servers connected; ..." if s.get("mcp") else None),
]
```

第 9 章回想出的记忆不放进 system prompt，而是用一条 `<system-reminder>` 消息注入对话。这样 prompt 前缀不会跟着记忆变动，cache 比较守得住。

### Prompt caching

大多数 system prompt 段落在一次 session 中是稳定的。demo 设了一个顶层的 cache 断点：

```python
client.messages.create(model=MODEL, system=assemble(DEMO_SECTIONS, state),
                       messages=messages, cache_control={"type": "ephemeral"})
```

稳定的内容应该排在易变的内容之前。如果一个会变动的值出现在前面，它可能会让更多 cache 失效。

Claude Code 也使用一个明确的动态边界。当较小的动态尾段变动时，这能保护一大段静态前缀。

### 如何整合

loop 在每次模型调用前组出 prompt：

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

---

## 各系统做法

每一轮如何组出 prompt。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 不会留着过时或不相关的指令。工具指引对得上启用中的工具集。 | 只从 config render 一次。没有东西要 memoize，也没有 cache 失效规则要管。 |
| **Cons** | 多了段落 registry、cache 失效规则，以及排序上的纪律。 | prompt 在 run 中途改不了。之后的状态只能以 observation 的形式进到模型。 |
| **Why** | 工具、记忆和模式会因 session 而异，prompt 要描述实际启用中的内容。 | 假设工具集在 run 中途不会变，开头 render 一次就一直有效。 |
| **How: assembly point** | 一个 prompt 组装器，每个段落各返回一个字符串。 | config 里的 Jinja2 template。变量缺了会直接报错。 |
| **How: sections** | 静态与动态段落。项目上下文以 context 消息注入。 | 两份 template：system 与 instance，变量来自 config、环境和运行期状态。 |
| **How: when built** | 每一轮从实时状态组出。动态段落会被记忆（memoize），直到 session 被清空或压缩。 | 只在 run 开始时组一次，并随平台调整。 |

---

## 哪里会出错

- **易变文字打坏 cache：**把会变动的内容放到后面，或放到 prompt 前缀之外。
- **段落 cache 过时：**当 session 状态改变时，清掉被记忆的段落。
- **Prompt 提到不存在的工具：**从实时启用的工具集生成工具文字。
- **上下文混进 prompt：**当项目文件、日期和 git 状态经常变动时，把它们放进 context 消息。
- **Prompt 覆盖互相冲突：**用单一 resolver 定义优先顺序。

---

## 可执行程序

[`src/`](src/) 承接 09 并加入：

- [`prompt.py`](src/prompt.py)：`Section`、`static` 和 `assemble`。
- [`loop.py`](src/loop.py)：每一轮重新组出 prompt。
- [`demo.py`](src/demo.py)：加入顶层的 `cache_control`。
- [`test.py`](src/test.py)：检查段落会依状态正确纳入或略过。

```bash
python sections/10-system-prompt/src/test.py         # offline checks, no key
uv run python sections/10-system-prompt/src/demo.py  # live demo, needs a key
```

---

## 来源

- [Claude Code 源码](https://github.com/yasasbanukaofficial/claude-code)：`constants/prompts.ts`、`constants/systemPromptSections.ts`、`utils/api.ts`、`QueryEngine.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`config/mini.yaml`、`agents/default.py` 的 `_render_template` 与 `get_template_vars`、`models/utils/cache_control.py`。
- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)：cache 断点、TTL、定价，以及 token 下限。
- [learn-claude-code · s10_system_prompt](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
