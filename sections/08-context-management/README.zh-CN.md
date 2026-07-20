# 8 · Context management

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 让长时间的 session 维持在 context limit 以内。

`messages[]` 会在执行过程中不断增长。每个 tool 结果、assistant 回复和 user turn 都会加入更多文字。长时间的 session 最终会碰到模型的 context limit。

context management 让 session 保持可用。它会在下一次 model call 之前，移除、用 stub 替换、持久化或摘要旧的内容。

当上下文被填满时：

1. API 可能会拒绝该请求。
2. 调用会变得更慢也更贵。
3. 旧的、比较没用的内容，会和当前任务的信息互相竞争。

没有这一层，一旦 prompt 塞不下，长任务就会失败。

---

## 机制

![机制图](assets/08-context-management.png)

在摘要之前先用低成本的 reducer。低成本的 reducer 是本地处理，而且大致上不损失信息。摘要则要付出一次 model call，而且可能丢失细节。

Claude Code 采用分层的顺序：

```text
budget   -> 把巨大的 tool 结果存到磁盘，留下一段预览
snip     -> 丢掉中段的旧轮次，保留开头和最近的结尾
micro    -> 把旧的 tool 结果本体换成一个 stub
collapse -> 可选的独立 context 系统
auto     -> 用 LLM 把整段历史摘要成一条消息
--- 以上都做了还是 prompt_too_long 时 ---
reactive -> 截掉开头并重新摘要，有重试上限
```

顺序很重要。举例来说，大型的 tool 结果应该先被持久化，之后任何 pass 才可以用 stub 替换它的本体。

### New: 缩减 pass

```python
def manage(messages, summarizer=None):                 # src/context.py, run every turn
    _budget(messages)                                  # persist huge results   (lossless)
    _micro(messages, KEEP_RECENT)                      # stub old result bodies (cheap)
    if summarizer and estimate_tokens(messages) > TOKEN_LIMIT:
        return _auto(messages, KEEP_RECENT, summarizer)  # summarize history (lossy, last resort)
    return messages
```

- `manage` 在每个 turn 执行低成本的 pass。
- `_budget` 把过大的 tool 结果写到磁盘，并留下一段简短的 preview。
- `_micro` 把旧的 tool 结果本体换成 stub。
- `_auto` 保留第一个 turn 和最近的尾端，然后摘要中间的部分。
- `summarizer=None` 在 demo 中禁用了会损失信息的摘要。

### 如何整合

context management 在每次 model call 之前执行：

```python
for _ in range(max_steps):                             # src/loop.py
    messages = context.manage(messages, summarizer=summarizer)   # 8 · keep context under the window
    response = model(messages, registry)
    ...
```

这一章动到的是 loop 本体。前几章加的都是 tool 或 dispatch 行为，loop 本身不用改。但 context 缩减必须在每次 model call 之前跑，所以只能写进 loop 里。

loop 仍然维持同样的不变条件：它用一个有效的 `messages[]` 调用模型，接着附上响应和任何 tool 结果。

---

## 各系统做法

各 agent 如何决定要腾出空间，以及要移除什么。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 长 session 撑得下去。多数缩减成本低，完整输出留在磁盘上，之后还能重读。 | 没有东西要调度、要调参，行为一眼就能看懂。 |
| **Cons** | 各个 pass 要讲究执行顺序。摘要可能丢掉模型之后会用到的细节。 | 历史只会成长。run 拖得比预算久，window 塞爆就直接中止。 |
| **Why** | 交互式 session 没有固定终点，window 迟早会满。 | 假设任务会先结束（提交或撞到成本上限，见第 21 章），轮不到 window 被塞满。 |
| **How: trigger** | token 阈值，外加 `prompt_too_long` 的反应式后备。 | 每条 observation，在 render 时处理。 |
| **How: strategy** | 先跑低成本 reducer（大结果存盘、旧结果清成 stub），最后才用 LLM 摘要。 | 过长的输出只保留头尾，没有压缩。 |
| **How: budget** | 保留 output 和安全缓冲空间。 | 每条 observation 上限一万字符。 |

---

## 哪里会出错

- **摘要漏掉需要的细节：**持久化完整输出，并在需要时重新读取文件。
- **压缩反复失败：**使用 retry 上限或断路器。
- **单个巨大 turn 仍然溢出：**对 `prompt_too_long` 做出反应，执行一次有界限的最后手段裁剪。
- **pass 顺序错误而丢失数据：**在把旧结果 stub 化之前，先持久化大型结果。
- **拆散的 tool 配对：**不要把一个 `tool_use` 和它相配的 `tool_result` 拆开。

---

## 可执行程序

[`src/`](src/) 沿用 07 并加上：

- [`context.py`](src/context.py)：`budget`、`micro` 和 `auto` 这几个 pass 都通过 `manage` 执行。
- [`loop.py`](src/loop.py)：在每个 turn 的最上方调用 `context.manage()`。
- [`test.py`](src/test.py)：独立检查每一个 pass。
- [`demo.py`](src/demo.py)：驱动已接上 context management 的 loop。

```bash
python sections/08-context-management/src/test.py         # offline checks, no key
uv run python sections/08-context-management/src/demo.py  # live demo, needs a key
```

---

## 来源

- [Claude Code 源码](https://github.com/yasasbanukaofficial/claude-code)：`services/compact/autoCompact.ts`、`microCompact.ts`、`timeBasedMCConfig.ts`、`compact.ts`、`utils/toolResultStorage.ts`、`query.ts`、`query/tokenBudget.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`config/mini.yaml` 的 observation template、`models/litellm_model.py` 的 `abort_exceptions`。
- [learn-claude-code · s08_context_compact](https://github.com/shareAI-lab/learn-claude-code)：章节框架。

以下是推测，在上面那份 Claude Code 源码 repo 里找不到完整实现：

- `snipCompact.ts`：只看得到 `snipCompactIfNeeded(messages)` 的调用点。
- `reactiveCompact.ts`：reactive 路径看起来位于 `compact.ts` 中。
