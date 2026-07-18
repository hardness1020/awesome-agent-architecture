# 2 · Tool runtime

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 新增一项能力，就是注册一个工具。循环维持不变。

agent 循环只能通过工具来行动。模型会发出一个结构化的 `tool_use` 区块，带有 `name` 与 `input`。

harness 把那个名称对应到代码。它验证输入、执行 handler，并返回结果。

这个 runtime 必须：

1. 告诉模型有哪些工具存在。
2. 描述每个工具的 input schema。
3. 依名称把每个 `tool_use` 路由出去。
4. 在可行时并行执行安全的调用。
5. 让庞大的工具目录仍可被探索。

没有这一层，模型能要求行动，却没有东西能真正执行那个行动。

如果只有一个 `bash` 工具，每一项能力都变成字符串处理。没有各别工具的验证或权限逻辑。

---

## 机制

```mermaid
flowchart LR
    R[("Registry · name -> tool")] -->|"schemas()"| M{{model call}}
    M -->|"tool_use · name + input"| D[lookup by name]
    R --> D
    D --> S{concurrency safe?}
    S -->|yes| P[parallel batch]
    S -->|no| Q[run in order]
    P --> T[tool_result]
    Q --> T
    T -->|append| M
```

一个工具是一个小对象，带有名称、handler、schema 与几个判定式。registry 依名称存放工具。dispatch 就是一次查表。

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

- 一个工具是一个 dataclass。
- registry 是 `name -> tool`。
- 新增一项能力，就是注册一个 handler。
- `schemas()` 返回向模型公告的工具清单。
- `run_concurrently` 会把标记为 `is_concurrency_safe` 的工具批量执行。
- 不安全的调用维持顺序执行，所以写入不会相互竞争。

### How it integrates

第 1 章用的是内嵌的 `HANDLERS` dict。第 2 章把一个 `registry` 传进循环，并把每个 `tool_use` 通过 `_dispatch` 路由：

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

循环主体其余部分维持不变。只有 dispatch 这一步现在改用 registry。

`_dispatch` 是下一个延伸点。第 3 章在那里加上权限关卡。第 4 章在那里加上 hook。

demo 为了清楚起见采用顺序 dispatch。真实的 runtime 会把安全调用批量化，并按需加载庞大的工具 schema。

---

## 各系统做法

各个 agent 如何定义工具、路由调用、处理并行，以及公开一份庞大目录。

| System | 工具定义 | Dispatch | 并行调用 | 探索 |
| --- | --- | --- | --- | --- |
| **Claude Code** | schema、handler 与判定式。 | 依名称查表，含别名。 | 安全调用批量执行。不安全调用顺序执行。 | 先给名称。schema 于请求时提供。 |

### Claude Code

- `buildTool` 设置安全的默认值。`isConcurrencySafe` 与 `isReadOnly` 默认为 `false`。
- `getAllBaseTools()` 列出内建工具，例如 `BashTool`、`FileReadTool`、`FileEditTool`、`GrepTool` 与 `AgentTool`。
- `getTools()` 与 `assembleToolPool()` 依权限筛选工具，并合并 MCP 工具。
- `findToolByName` 依 `name` 与 `aliases` 解析。
- `partitionToolCalls` 把 concurrency-safe 的调用分组，通过 `runToolsConcurrently` 执行。
- 不安全的调用会打断批次，单独执行。
- 标记为 `shouldDefer` 的工具先以名称出货。`ToolSearchTool` 依精确名称或关键字加载完整 schema。

> **取舍：** 每个工具一个对象模型，带来验证、权限、安全的并行，以及延迟探索。
> 它同时也让每个工具都要背负一份契约。
> 单一 `bash` 工具比较小，但它无法分别验证输入或把关行动。

---

## 失效模式

- **未知的工具名称：**模型指名了一个不存在或已停用的工具。返回一个 `tool_result` 错误，而不是让循环崩溃。
- **schema 漂移：**schema 说一套，handler 期待另一套。在 dispatch 前先验证。
- **不安全的并行：**两个写入可能损毁同一个文件。默认采用顺序执行，除非确知某工具是安全的。
- **目录溢出：**太多工具 schema 会挤爆 prompt。把完整 schema 延后到需要时再给。
- **结果过大：**庞大的输出可能塞满 context window。限制结果大小、保存完整输出，并返回一段预览加一个路径。

---

## 可执行程序

[`src/`](src/) 承接 01 往前走，并加上：

- [`tools.py`](src/tools.py)：`Tool`、`Registry` 与 `run_concurrently`。
- [`loop.py`](src/loop.py)：把每个 `tool_use` 通过 `Registry` dispatch。
- [`demo.py`](src/demo.py)：注册一个 `ReadFile` 工具，并对着 API 执行循环。
- [`test.py`](src/test.py)：检查 dispatch、未知工具错误与并行批次。

```bash
python sections/02-tool-runtime/src/test.py         # offline checks, no key
uv run python sections/02-tool-runtime/src/demo.py  # live demo, needs a key
```

---

## 出处

- Claude Code source：`Tool.ts`、`tools.ts`、`services/tools/toolOrchestration.ts`、`services/tools/toolExecution.ts`、`tools/ToolSearchTool/ToolSearchTool.ts`。
- learn-claude-code · s02_tool_use：章节框架。
