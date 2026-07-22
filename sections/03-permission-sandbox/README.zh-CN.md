# 3 · Permission & sandbox

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 每个动作在真正碰到系统之前，都要先检查。

模型可以要求执行任何已启用的工具。permission 层负责决定该次调用是否可以执行。

一个没有 permission 的工具执行环境，几乎等同于一个无人看管的远程 shell。

一次错误的工具调用可能删除文件、泄漏机密，或推送错误的代码。信任模型不是一道安全边界。程序必须在执行前检查请求。

permission 层必须做到：

1. 在每个工具调用执行前先检视它。
2. 决定 `allow`、`ask` 或 `deny`。
3. 当高风险的调用尚未预先核准时，询问用户。
4. 当调用真的执行时，限制它造成的损害。

没有这一层，一次错误的工具调用就可能造成无法恢复的后果。

---

## 机制

![机制图](assets/03-permission-and-sandbox.png)

一个纯函数负责做出 permission 决策。它读取工具、当前的 mode，以及所有的 allow 规则，并返回三个值之一：

- `allow`：执行工具。
- `ask`：暂停并询问用户。
- `deny`：不执行工具。

mode 会改变默认行为。举例来说，plan mode 允许只读工具，但在计划核准前拒绝编辑。

### New: the gate

`decide()` 就是整个 permission 决策：

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

这个函数没有 I/O。这让它可以一个 mode 一个 mode 地轻松测试。

### How it integrates

gate 在 `_dispatch` 内部执行，就在 `run_tool` 之前：

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

- loop 主体和第 1、2 章相同，没有改变。
- 只有 `_dispatch` 多了 gate。
- `deny` 以及未核准的 `ask` 永远不会抵达 `run_tool`。
- 拒绝结果仍会以 `tool_result` 返回，所以模型看得到发生了什么，并能随之调整。
- `approver` 默认为 `False`，所以 `ask` 代表“否”，除非用户核准。

关键不变条件维持不变：每个工具调用都会产生一条结果消息，即使真正的动作没有执行。

真实系统会加上规则优先级、记住的核准，以及沙箱化的执行。这些都是同一个 gate 的延伸。

---

## 各系统做法

各个 agent 如何管制副作用、切换 mode，以及记住决策。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | mode、有序规则与沙箱化提供精确的控制。 | 几分钟就能审计完。拒绝会落回对话，模型读得到原因，loop 继续跑。 |
| **Cons** | 要推敲的状态很多。每条 bypass 或预先核准的路径都必须保持可见且范围狭窄。 | 对每条命令一视同仁，而且什么都不记。 |
| **Why** | 每次调用都问会造成核准疲劳，所以系统会把核准记下来。 | 损害交给环境去限制，一个确认提示加一份 regex 清单就够了。 |
| **How: gate point** | 每个工具执行前。Web、MCP 与远程执行各有核准路径。 | 每一步的命令执行前。按 Enter 就核准，留言就是拒绝。 |
| **How: permission modes** | Default、edit-approved、plan、deny 与 bypass，另有内部 mode。 | `human`、`confirm` 与 `yolo`，运行期可用斜杠命令切换。 |
| **How: sandbox** | Bash 可以在沙箱内执行。 | 环境 class 就是沙箱，每次运行挑：主机本身、用完即丢的容器，或在共用主机上包住执行。 |
| **How: rule persistence** | 规则依优先级从多个来源合并，可存到 session 或 settings。 | 白名单 regex 只写在 config，匹配的命令跳过确认。 |

---

## 哪里会出错

- **Pattern-match bypass：**字符串式的 deny 清单会漏掉 shell 的各种变体。优先采用行为检查与沙箱化，而不是原始的子字符串比对。
- **Mode 开得太宽：**一条范围过大的 allow 规则或 bypass mode，可能让后续的高风险调用悄悄执行。限缩 bypass 的范围，并让当前的 mode 显示出来。
- **核准疲劳：**每次调用都询问，会训练用户不看内容就核准。预先核准低风险的类别，但让破坏性动作维持明确询问。
- **subagent 内的无声拒绝：**子 agent 可能没有终端可以询问。应把提示往上冒泡给父 agent，而不是无声失败。
- **沙箱被停用：**若一个被允许的指令在沙箱外执行，permission 提示就是最后一道检查。任何未沙箱化的路径都要用策略挡在后面。

---

## 可执行程序

[`src/`](src/) 承接 02 并加上：

- [`permissions.py`](src/permissions.py)：涵盖四种 mode 的 `decide`。
- [`loop.py`](src/loop.py)：在 `_dispatch` 中于执行前管制每个调用。

```bash
python sections/03-permission-sandbox/src/test.py         # offline checks, no key
uv run python sections/03-permission-sandbox/src/demo.py  # live demo, needs a key
```

---

## 出处

- [Claude Code 源码](https://github.com/yasasbanukaofficial/claude-code)：`QueryEngine.ts`、`hooks/useCanUseTool.tsx`、`types/permissions.ts`、`utils/permissions/PermissionUpdate.ts`。
- [Claude Code 沙箱与 web gate](https://github.com/yasasbanukaofficial/claude-code)：`tools/BashTool/shouldUseSandbox.ts`、`tools/WebFetchTool/preapproved.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`agents/interactive.py`、`environments/docker.py`、`environments/extra/bubblewrap.py`。
- [learn-claude-code · s03_permission](https://github.com/shareAI-lab/learn-claude-code)：section framing。
