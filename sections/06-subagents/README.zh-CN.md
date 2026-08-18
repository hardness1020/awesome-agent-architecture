# 6 · Subagents

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 运行一个聚焦的子 loop，只返回它的结果。

主 agent 可以把工作派给 subagent：派工作的那端叫 parent，被派出去的叫 child。

对 parent 来说，这只是一次 tool call。但这次调用里面跑的，是一个完整的 agent loop。parent 给 child 一段 prompt。child 拿到全新的 `messages[]`，一路运行到完成，然后返回它的最终答案。

这样可以把旁支调查排除在 parent 的情境之外。parent 不需要 child 读过的每个文件或每个命令结果。它通常只需要结论。

没有 subagents 的话，每一次调查都会留在主 transcript 里。长时间运行会变得杂乱、昂贵，也更难让模型跟上。

---

## 机制

![机制图](assets/06-subagents.png)

一个 `Agent` tool 会启动一个 child agent。child 有自己的 session 和 message 列表。它跑的是和 parent 一样的 loop。

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

loop 不会改变。subagent 只是另一个调用 loop 的 tool handler。

有三个特性很重要：

- **全新情境：**child 不会继承 parent 的 transcript。parent 也不会继承 child 的轨迹。
- **继承的权限：**child 会复制 parent 的 permission mode 和 allow rules。情境隔离不等于权限隔离。
- **递归上限：**这个 demo 从 child registry 中省略了 `Agent`，所以 child 无法再生出另一个 child。

---

## 各系统做法

各 agent 如何隔离一个子问题，并返回结果。

| | Claude Code | deepseek-harness |
| --- | --- | --- |
| **Pros** | child 的情境让 parent 保持聚焦，主 transcript 也干净。 | 同一个接缝涵盖进程内的 child、外部 runtime，以及产品 CLI。 |
| **Cons** | parent 不知道 child 是怎么得出答案的，摘要太薄就得再问一次。 | 一个工具能解决的事，这里有六种后端加一套续跑管理。 |
| **Why** | parent 只需要结论，不需要 child 读过的每个文件。 | 委派只是传输方式的选择，所以每种后端都挂在一个名字下。 |
| **How: spawn primitive** | `Agent` tool。用 subagent type 选一个内置 persona。 | 每个注册的后端各有一个工具：全新 child、fork、外部 runtime 或 CLI。 |
| **How: context isolation** | child 的 messages 是全新的，不带 parent 的 transcript。 | 全新 child 从空的开始。fork 只复制 parent 已经跑完的 turn。 |
| **How: result return** | child 最后一则消息的文本返回给 parent，transcript 丢弃。 | 最后一则 assistant 消息，外加可选的结构化输出，会按 schema 检查。 |
| **How: resume** | 多数 agent 可以续跑，parent 再发一条消息就行。 | durable 的 child 会把后续消息排进队列，重启后也能从 log 重新载回。 |

---

## 哪里会出错

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

- [Claude Code 源码](https://github.com/yasasbanukaofficial/claude-code)：
  `tools/AgentTool/AgentTool.tsx`、`runAgent.ts`、`resumeAgent.ts`、`forkSubagent.ts`、`builtInAgents.ts`、`tasks/LocalAgentTask/`。
- [deepseek-harness source](https://github.com/deepseek-ai/deepseek-harness)（`dsh-v0.1.0-rc.7`）：
  `packages/subagent/subagent/src/index.ts`、`src/continuation.ts`、`packages/subagent/subagent-fork-in-process/README.md`、
  `packages/subagent/subagent-acp/README.md`、`docs/subsystems/subagent.md`、`docs/tool-catalog.md`。
- [learn-claude-code · s06_subagent](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
