# 6 · Subagents

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 运行一个聚焦的子循环，只返回它的结果。

subagent 就是在一次 tool call 里运行的 agent 循环。parent 给 child 一段 prompt。child 拿到全新的 `messages[]`，一路运行到完成，然后返回它的最终答案。

这样可以把旁支调查排除在 parent 的情境之外。parent 不需要 child 读过的每个文件或每个命令结果。它通常只需要结论。

没有 subagents 的话，每一次调查都会留在主 transcript 里。长时间运行会变得杂乱、昂贵，也更难让模型跟上。

---

## 机制

```mermaid
flowchart LR
    subgraph parent[Parent loop]
        M{{model call}} -->|"tool_use · Agent"| A[Agent tool]
        T["tool_result · final text"] --> M
    end
    subgraph child["Child · fresh messages[]"]
        S["new Session · inherited mode + rules"] --> L{{run_turn}}
        L -.-> X[transcript discarded]
    end
    A -->|child prompt| S
    L -->|final text only| T
```

一个 `Agent` tool 会启动一个 child agent。child 有自己的 session 和 message 列表。它跑的是和 parent 一样的循环。

只有 child 的最终文本会返回。它的 transcript 会被丢弃。文件写入和 shell 的副作用仍然会发生在工作目录里。

### New: the Agent tool

```python
def agent_tool(model, child_registry, parent_session):     # src/subagents.py
    def spawn(a):
        child = Session(mode=parent_session.mode,          # fresh context, inherited authority
                        allow_rules=set(parent_session.allow_rules))
        messages = [{"role": "user", "content": a["description"]}]   # the child's own conversation
        return run_turn(messages, model, child_registry, child)      # the loop, run again
    return Tool("Agent", spawn, is_read_only=True)
```

- `agent_tool` 返回一个普通的 tool。
- 它的 handler 用一个新的 `Session` 调用 `run_turn()`。
- child 的 `messages[]` 一开始只有 child 的 prompt。
- child 返回 `run_turn()` 所返回的文本。

### How it integrates

循环不会改变。subagent 只是另一个调用循环的 tool handler。

有三个特性很重要：

- **全新情境。** child 不会继承 parent 的 transcript。parent 也不会继承 child 的轨迹。
- **继承的权限。** child 会复制 parent 的 permission mode 和 allow rules。情境隔离不等于权限隔离。
- **递归上限。** 这个 demo 从 child registry 中省略了 `Agent`，所以 child 无法再生出另一个 child。

---

## 各系统做法

各 agent 如何隔离一个子问题，并返回结果。

| System | Spawn primitive | Context isolation | Result return | Resume |
| --- | --- | --- | --- | --- |
| **Claude Code** | `Agent` tool。 | child 的 messages 是全新的。 | child 最后一则消息的文本。 | 多数 agent 可以续跑。 |

### Claude Code

- 这个 tool 位于 `tools/AgentTool/AgentTool.tsx`。
- 旧的 wire 名称是 `Task`。
- `subagent_type` 用来选择一个内置 persona。
- 内置的包含 general-purpose、explore、plan、status-line setup、guide 和 verification agent。
- child 循环在 `runAgent.ts` 中运行，带着全新的 `initialMessages`。
- `extractTextContent` 把最后一则消息返回给 parent。
- `isInForkChild` 防止递归的 fork spawning。
- 后台 subagent 会变成 `LocalAgentTask`。
- 多数 agent 可以通过 `SendMessage` 和 `resumeAgent.ts` 继续运行。

> **取舍：** child 的情境让 parent 保持聚焦。
> parent 同时也失去了 child 是如何得出答案的细节。
> 如果摘要太单薄，parent 就必须再问一次，或去读 child 写下的文件。

---

## 失效模式

- **摘要遗漏信息：**child 可能压缩过头。要求它把重要发现写到磁盘上。
- **失控递归：**child 生 child 可能无上限地增长。从 child registry 省略 `Agent` tool，或强制设一个深度上限。
- **child 停不下来：**child 和 parent 有一样的停止风险。给每个 child 自己的 turn 或 token 上限。
- **误以为有权限隔离：**child 仍然需要正常的 permission gate。不要因为情境是分开的就跳过它。
- **孤儿异步 child：**一个后台 child 可能在 parent 已经往前走之后才结束。用一条 task 记录来追踪它。

---

## 可执行程序

[`src/`](src/) 沿用 05 并加上：

- [`subagents.py`](src/subagents.py)：`Agent` tool。
- [`loop.py`](src/loop.py)：与第 5 章相同，未变动。
- [`demo.py`](src/demo.py)：parent 把一个计数任务委派给 child。
- [`test.py`](src/test.py)：检查全新情境、继承的权限，以及递归防护。

```bash
python sections/06-subagents/src/test.py         # offline checks, no key
uv run python sections/06-subagents/src/demo.py  # live demo, needs a key
```

---

## 出处

- Claude Code 源码：`tools/AgentTool/AgentTool.tsx`、`runAgent.ts`、`resumeAgent.ts`、`forkSubagent.ts`、`builtInAgents.ts`、`tasks/LocalAgentTask/`。
- learn-claude-code · s06_subagent：章节框架。
