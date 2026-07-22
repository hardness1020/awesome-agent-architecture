# 19 · MCP / plugins / channels

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 能力不够？插进更多。harness 靠一套标准 protocol 接上外面的世界。

一个 harness（外层架构）只能做它的工具允许它做的事，而每个内建工具都是预先定义好的：input schema、执行逻辑、错误处理，全都是。

这无法扩展到用户想要的各种服务：issue tracker、部署系统、知识库。你没办法为每一个服务、用它各自的语言，都写一个专属工具。

MCP（Model Context Protocol）就是填补这道缺口的开放标准。一个外部服务宣告它的工具，agent 则盲调用它们，不需要知道是谁写的、怎么写的。

于是 agent 不需要任何人动 harness，就得到了 Jira 工具或部署工具。少了 MCP，agent 的能力就停在安装当下内建的那一套，之后加不了新的。

MCP 之外，这一章还讲两个搭在它上面的机制：plugin 把 server 跟 hook、skill 打包在一起，让人一次装好；channel 则让 server 能主动把消息推回来。两者都跑在同一套 protocol 上。

---

## 机制

![机制图](assets/19-mcp-plugins-channels.png)

连上每个 server，探索它的工具（`tools/list`），把每个工具包装成一个 runtime `Tool`（第 2 章），再把这些合并进 loop 用来 dispatch 的同一个工具池。

名称以 `mcp__<server>__<tool>` 加上命名空间，所以两个 server 永远不会撞名。loop 与 gate 都不变：一个 MCP 工具就是一个 `Tool`，只是它的 `run()` 会通过 transport 对外调用。

- 对每个 server 调用一次 `tools/list`，问它有哪些工具；返回清单里的每一条规格，都被包成一个 `Tool`。
- 名称加了命名空间并经过正规化，所以它是唯一的，也符合 API 的名称样式。
- 每个工具的 MCP annotation（`readOnlyHint`、`destructiveHint`）成为 gate 读取的权限提示（第 3 章）。
- 合并进那一个 `Registry` 之后，模型会在同一份清单里看到 MCP 工具与内建工具。

### New: 包装探索到的工具

`mcp.py` 把每个探索到的规格变成一个 `Tool`。名称加上命名空间让 server 永不撞名，并正规化到符合 API 的字符集：

```python
def tool_name(server, tool):                           # src/mcp.py
    return f"mcp__{normalize(server)}__{normalize(tool)}"   # buildMcpToolName

def wrap(server, spec, call):
    ann = spec.get("annotations", {})
    read_only = bool(ann.get("readOnlyHint"))
    bare = spec["name"]
    return Tool(
        name=tool_name(server, bare),
        run=lambda args, _t=bare: call(_t, args),      # dispatch calls out over the transport
        input_schema=spec.get("inputSchema") or dict(NO_INPUT),
        is_read_only=read_only,
        is_concurrency_safe=read_only,                 # reads are safe to batch
    )
```

- `tool_name` 为每个工具加上命名空间；`normalize` 把任何落在 `[a-zA-Z0-9_-]` 之外的字符换成 `_`，以符合 API 名称样式。
- `run` 捕捉了裸工具名与 server 的 `call`，所以 dispatch 被包装的 `Tool` 时会通过 transport 回调过去。
- `readOnlyHint` annotation 成为 `is_read_only`，这正是权限 gate（第 3 章）用来决定放行或询问的依据。

### New: 探索与合并

`connect` 执行一次探索并返回被包装的工具；调用端把它们合并进 loop 的 `Registry`：

```python
def connect(server, conn):                             # src/mcp.py
    return [wrap(server, spec, conn.call) for spec in conn.list_tools()]
```

- `conn` 是一个活的 transport：正式环境是 `stdio` 或 `http`，demo 里是 in-process。探索并不在意是哪一种。
- 返回的 `Tool` 注册进与内建工具同一个池，所以 `registry.schemas()` 会把它们一起公告，loop 也以相同方式 dispatch。

### New: channel 与 plugin 配置

这一章还剩两个小机制。

第一个是反向的消息流：平常是 agent 去调用 server，但 server 也可以主动把消息推进来，例如一条 Slack 消息到了。harness 把这段文字包上 `<channel>` 标签，接在 agent 下一轮输入的前面，模型就会读到它：

```python
def wrap_channel(source, payload):                     # src/mcp.py
    return f'<{CHANNEL_TAG} source="{source}">{payload}</{CHANNEL_TAG}>'
```

第二个是配置的叠加：同一个 server 可能同时出现在 plugin、用户和项目的配置里，`merge_servers` 按优先级决定谁生效：

```python
def merge_servers(*layers):                            # src/mcp.py
    merged = {}
    for scope in PRECEDENCE:                            # plugin < user < project < local
        for layer in layers:
            merged.update(layer.get(scope, {}))
    return merged
```

- `wrap_channel` 把 Slack、Discord 或 SMS 变成同一套 protocol 上的双向接口；带标签的区块像一条背景备注一样进入队列（第 13 章）。
- `merge_servers` 解决一个在多个 scope 都有定义的 server：`local` 覆盖 `project`，`project` 覆盖 `user`，`user` 覆盖 `plugin`。

channel 的消息谁都能发：从 Slack 或 SMS 进来的文字不一定出自用户本人，可能是垃圾消息，甚至是想操纵 agent 的指令。所以消息得先通过 gate 检查，才能变成一个 turn（Hermes 对每条进来的消息，在 auth 之前就 fire `pre_gateway_dispatch`）：

```python
def gate_inbound(source, payload, gates=()):           # src/mcp.py
    for gate in gates:
        out = gate(source, payload) or {}
        if out.get("drop"):
            return None                                # discarded: the model never reads it
        if out.get("rewrite") is not None:
            payload = out["rewrite"]                   # e.g. redact a secret
    return wrap_channel(source, payload)
```

- 一个 gate 可以 drop（垃圾消息、不明发件人）或 rewrite（遮蔽机密），发生在 loop 看到文字之前。
- 返回 `None` 代表这条消息不会变成任何 turn，垃圾输入连一次模型调用都不用花。

### 如何整合

demo 探索一个 server 并跑一轮 agent。模型盲调用这个 MCP 工具：

```python
reg = Registry()
for t in mcp.connect("kb", KBServer()):                # discover, wrap, merge
    reg.register(t)
run_turn([...goal...], model, reg, Session(mode=DEFAULT))   # the one agent call
```

- 模型在它的工具清单里看到 `mcp__kb__search` 就在任何内建工具旁边，并调用它；它永远不会得知是谁写了这个工具。
- 这个工具是只读的，所以 gate 不提示就放行。一个具破坏性的工具则会询问，或由一条以完整名称为键的规则预先核准。
- loop 不变。MCP 只是往池里加工具；下游的一切都是第 2 章的 dispatch 与第 3 章的 gating。

---

## 各系统做法

harness 如何伸手触及自身之外。

| | Claude Code | Hermes Agent |
| --- | --- | --- |
| **Pros** | 任何服务、任何语言都接得上，不用改 harness。loop 与 gate 都不变。 | 其他 client 能把它当 MCP server 来用。每条从平台进来的消息都先过 gate。 |
| **Cons** | 每个连上的 server 都是新的攻击面，annotation 又是自我陈报的。工具清单会膨胀。 | channel 的消息谁都能发：垃圾消息、想操纵 agent 的指令也会进来。 |
| **Why** | 少了 MCP，能力就停在安装当下内建的那一套。 | agent 同时是 MCP client 和 MCP server，聊天平台就是它的双向接口。 |
| **How: transports** | 六种，从 stdio 到 http/sse/ws。本地与远端 server 各连各的池。 | MCP 双向，加上聊天平台 adapter。语音走同样的 channel。 |
| **How: plugin format** | 一个 plugin 打包 server、hook、skill。配置按优先级分层合并。 | 一份 manifest 加一个注册入口。要覆盖内建工具，操作者得明确同意。 |
| **How: tool pool assembly** | 每个 server 工具被复制、加命名空间，并与内建工具合并。annotation 成为 gate 的权限提示。 | plugin 与 MCP 工具加入同一个 import 时建立的 registry。 |

---

## 哪里会出错

- **撞名（Name collisions）：**两个 server 都公开 `search`。`mcp__server__tool` 命名空间避免了冲突；但一个名称含 `__` 的 server 仍会被解析错误，所以名称要保持简单。
- **工具清单膨胀（Tool-list bloat）：**太多 server 会造成庞大的工具清单，既花 token 又干扰选择（第 2 章）。缓解：截断描述并延后载入。
- **connect 之后池过时：**一个在 session 中途加入的 server 不在 cache 的工具清单里，于是模型永远看不到它。缓解：变动时重建池并重建 prompt（第 8 章）。
- **连接抖动（Connection churn）：**一个不稳的 server 会超时、重置，或 token 过期。缓解：反复失败后重连、`401` 时重新验证、为每次调用设超时（第 11 章）。
- **被过度信任的副作用：**一个 server 把具破坏性的工具标成 `readOnlyHint: true` 以跳过提示。缓解：以完整名称设一条规则照样 gate 它（第 3 章）。

---

## 可执行程序

[`src/`](src/) 承接第 18 章并加上：

- [`mcp.py`](src/mcp.py)：探索与包装、plugin 配置合并、channel 包装，以及入站 gate（`gate_inbound`）。
- [`test.py`](src/test.py)：探索与命名空间、权限提示的对应、连同 gate 合并进池、配置优先级、channel 标签，以及入站的 drop 与 rewrite。
- [`demo.py`](src/demo.py)：一轮 agent 通过探索到的 `mcp__kb__search` 盲调用一个 in-process MCP 工具。

loop 与 dispatch 都不变。MCP 只是往第 2 章的池里加工具；第 3 章的 gate 读取它们自我宣告的 annotation。

```bash
python sections/19-mcp-plugins-channels/src/test.py         # offline checks, no key
uv run python sections/19-mcp-plugins-channels/src/demo.py  # live demo, needs a key
```

---

## 来源

- [Claude Code MCP transport](https://github.com/yasasbanukaofficial/claude-code)：`services/mcp/types.ts`（`TransportSchema`）、`client.ts`（`MCPTool` cloning、`buildMcpToolName`）、`normalization.ts`（`normalizeNameForMCP`）。
- [Claude Code MCP config and channels](https://github.com/yasasbanukaofficial/claude-code)：`config.ts`（precedence）、`channelNotification.ts`（`CHANNEL_TAG`），加上 `McpAuthTool`、`ListMcpResourcesTool`、`ReadMcpResourceTool`。
- [Claude Code plugins](https://github.com/yasasbanukaofficial/claude-code)：`plugins/builtinPlugins.ts`、`plugins/bundled/`、`types/plugin.ts`，加上 `remote/` 与 `bridge/`。
- [Hermes Agent 源码](https://github.com/NousResearch/hermes-agent)：`mcp_serve.py`、`hermes_cli/plugins.py`（`PluginManager`、`VALID_HOOKS`）、`gateway/platforms/`、`gateway/platform_registry.py`、`plugins/platforms/`。
- 章节定位：[learn-claude-code · s19_mcp_plugin](https://github.com/shareAI-lab/learn-claude-code)。
