# 1 · Agent Loop

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 一个 loop 不断调用模型，直到它给出答案或要求使用工具。

单纯调用模型就是一问一答。你把 messages 发过去，它回你一次，就结束了。

agent 需要多一个步骤。它必须执行模型要求的工具、把结果附加回去，再次调用模型。同一份 `messages[]` 必须在整轮中持续成长。

这个 loop 必须：

1. 在多次调用之间保留对话状态。
2. 分辨是使用工具，还是最终答案。
3. 执行被要求的工具，并把结果附加回去。
4. 反复调用模型，直到它停下来。

没有这个 loop，模型能对行动进行推理，却无法行动。如果 loop 写错，它不是太早停止，就是永远跑下去。

---

## 机制

![机制图](assets/01-agent-loop.png)

这里是两个 loop 共用同一份 `messages[]`。

拿聊天窗口来想象。你问“北京现在天气如何？要不要带伞？”，模型可能先调用查天气的工具，拿到结果后再调用查降雨概率的工具，最后才回你答案。
**所以同一个轮次里，模型往往被调用好几次，中间穿插各种工具调用。**
这整段从提问到答完就是**内层 loop**，也就是一个用户轮次（turn）：它调用模型、检查 `stop_reason`、需要时执行工具、把结果附加回去，然后重复，直到模型给出这一轮的最终答案。

接着你在同一个窗口再问“那明天呢？”，这就是新的一轮。
把一轮又一轮串成整段对话的，就是**外层 loop**。每个新轮次都附加到同一份 `messages[]`，所以模型在回答“明天”时，看得到你前面问过北京的天气，你不必再说一次。

内层 loop 就是拿着调用端手上那份 `messages[]`，把一轮跑完：

```python
def run_turn(messages, model, max_steps=10):        # src/loop.py · one turn over the shared messages[]
    for _ in range(max_steps):                       # the inner loop, with a backstop
        response = model(messages)                   # one Anthropic Messages call
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":       # model produced its answer for this turn
            return final_text(response)

        results = []                                 # tool_use: run each, feed back
        for block in response.content:
            if block.type == "tool_use":
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": run_tool(block.name, block.input)})
        messages.append({"role": "user", "content": results})

    raise RuntimeError("hit max_steps without end_turn")
```

- [`src/loop.py`](src/loop.py) 中的 `run_turn()` 就是内层 loop。
- `messages` 是采用 Anthropic Messages 格式的共享状态。
- `max_steps` 是防止 loop 失控的安全上限。
- `run_tool(name, input)` 解析出工具、执行它，并返回供 `tool_result` 使用的文字。
- [`src/demo.py`](src/demo.py) 中的 `model()` 是一次 `client.messages.create` 调用。loop 不绑定单一供应商。

外层 loop 每一轮附加一条用户消息，并保留整个缓冲区：

```python
messages = []                                        # src/demo.py · the conversation, owned by the caller
for user_text in turns:                              # the outer loop: one iteration per user turn
    messages.append({"role": "user", "content": user_text})
    reply = run_turn(messages, model)                # appends in place; turn N sees turns 1..N-1
```

有两个 `stop_reason` 值驱动这个 loop：

- `tool_use`：执行工具、附加结果，再次调用模型。
- `end_turn`：返回最终答案。demo 只要遇到任何不是 `tool_use` 的值就停止。

`messages[]` 是这个 session 的整段对话记忆。工具结果与 assistant 回复都会放进去。下一次模型调用会在这整份状态上进行推理。

这个最精简的 loop 没有权限关卡。第 3 章会在工具执行前加上权限。

---

## 各系统做法

各个 agent 如何拥有这个 loop，以及如何决定何时停止。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 能流式传输进度、把关副作用，还能并行执行工具。 | loop 很小，容易阅读与审计。 |
| **Cons** | loop 包在一个更大的 runtime 里，不能单独拿出来用。 | 无法把关副作用、流式传输进度，或并行执行工具。 |
| **Why** | 核心分支保持不变，功能都加在外围。 | 小 loop 本身就是目的。检测任务是否完成的是环境，不是模型。 |
| **How: loop driver** | 一个 async generator。每个工具通过同一份契约接进 dispatch。 | 一个 while loop。每一步跟模型要一条命令，再执行。 |
| **How: stop signal** | `stop_reason: end_turn`。 | 附加一条 `role: "exit"` 消息。由环境检测提交标记。没带命令的响应只算格式错误。 |
| **How: parallel tools** | 有。同一次模型轮次中的工具调用可以并行执行。 | 没有，action 依序执行。 |
| **How: streaming** | 有。模型 token、工具调用与工具结果发生的当下就逐一送出。 | 没有。 |

---

## 哪里会出错

- **没有停止条件：**一个 bug 或工具 loop 可能永远跑下去。用最大步数或 token 上限。
- **loop 中途 context overflow：**`messages[]` 只会成长。第 8 章加上 context 管理。
- **部分工具失败：**失败的工具仍必须返回一个 `tool_result`，模型才能恢复。
- **结果丢失：**丢掉 assistant 的工具调用或工具结果任何一个，都会破坏 transcript。两者都要附加。

---

## 可执行程序

[`src/`](src/) 从这里开启整条链：

- [`loop.py`](src/loop.py)：内层 loop 与共享的 `messages[]`。
- [`demo.py`](src/demo.py)：两轮的实时 demo。第 2 轮依赖第 1 轮仍留在缓冲区里。
- [`test.py`](src/test.py)：针对工具 dispatch、最终文字与多轮状态的离线检查。

第 2 到 11 章会把这份 `src/` 带着往前走，持续演进 `loop.py`，并在每一章加上一个文件。

```bash
python sections/01-agent-loop/src/test.py         # offline checks, no key
uv run python sections/01-agent-loop/src/demo.py  # live demo, needs a key
```

---

## 出处

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code)：`QueryEngine.ts`、`query/`、`Tool.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`agents/default.py`、`exceptions.py`、`environments/local.py`。
- [learn-claude-code · s01 Agent Loop](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
