# 4 · Hooks

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> hook 在循环周围的固定点加入行为。

hook 是用户配置的 callback。它们可以在工具调用前、工具调用后、prompt 发送时，或 session 开始或结束时运行。

用 hook 来做记录、验证、通知，以及小型的策略检查。没有 hook，每一个新行为都得改动循环或另外分叉它。

hook 让循环保持精简。循环对外提供固定的事件。扩展行为则挂接到那些事件上。

---

## 机制

![机制图](assets/04-hooks.png)

一个 `Hooks` 对象把事件名称映射到 callback 列表。循环不会直接调用自定义的检查。取而代之，`_dispatch` 触发具名的事件。

在工具执行方面，有两个重要的点：

- `PreToolUse` 在 permission gate 之前运行。它可以拦截调用，或改写输入。
- `PostToolUse` 在工具调用成功之后运行。它可以观察结果。

### New: hooks

```python
class Hooks:                                     # src/hooks.py
    def fire_pre(self, name, args):               # PreToolUse: block or rewrite
        for fn in self._hooks["PreToolUse"]:
            out = fn(name, args) or {}
            if out.get("updated_args"): args = out["updated_args"]
            if out.get("deny"):         return True, args, out.get("message", "")
        return False, args, ""
    def fire_post(self, name, args, result):      # PostToolUse: observe
        for fn in self._hooks["PostToolUse"]: fn(name, args, result)
```

- `on(event, fn)` 注册一个 callback。
- `fire_pre` 运行 `PreToolUse` 的 callback。
- pre-hook 可以返回 `{"deny": True}` 来拦截调用。
- pre-hook 可以返回 `{"updated_args": ...}` 来改写输入。
- `fire_post` 在执行之后运行观察者。

### How it integrates

`_dispatch` 加入了两个调用：

```python
# src/loop.py _dispatch
blocked, args, msg = hooks.fire_pre(name, args)          # 4 · PreToolUse
if blocked: return res(msg)
decision = permissions.decide(tool, mode, allow_rules)   # 3 · gate (section 3)
...                                                      # deny / ask short-circuit
out = res(run_tool(tool, args))                          # 2 · execute -> tool_result
hooks.fire_post(name, args, out)                         # 4 · PostToolUse
```

- 被拦截或被拒绝的调用永远不会到达 `run_tool`。
- `PostToolUse` 只在成功执行之后才会运行。
- hook 可以收紧 permission 的结果，但不应该放宽它。
- 在 Claude Code 中，`resolveHookPermissionDecision` 会把 hook 输出和基于规则的 permission 加以协调。

demo 用一个 `PreToolUse` hook，即使在 `bypassPermissions` 之下也拦截 `rm -rf`。

本章谈的是生命周期 hook。放在 `hooks/` 文件夹中的 React render hook，是不相干的 UI 代码，只是共用同一个词。

---

## 各系统做法

各个 agent 如何在循环周围提供拦截点。

| System | Hook events | Fire point | Can block or modify? |
| --- | --- | --- | --- |
| **Claude Code** | 固定的生命周期事件。 | 从 settings 配置。`PreToolUse` 在 gate 之前运行。 | 可以。拒绝、询问、更新输入、加入 context，或停止。 |

### Claude Code

- `HOOK_EVENTS` 定义了 27 个生命周期事件。
- 重要事件包含 tool、prompt、session、stop、subagent、compact 与 setup 等事件。
- hook 从 `.claude/settings.json` 加载。
- `captureHooksConfigSnapshot()` 在启动时冻结当前生效的 hook 集合。
- `toolExecution.ts` 在解析 permission 之前运行 `runPreToolUseHooks`。
- `HookResult` 可以包含 `permissionBehavior`、`updatedInput`、`additionalContext`、`preventContinuation` 与 `blockingError`。

> **取舍：** hook 让用户不必改动循环就能扩展行为。而固定的事件列表同时也是它的边界。hook 只能在系统对外提供事件的地方进行拦截。

---

## 失效模式

- **hook 绕过 permission：**hook 可能试图允许一个已被拒绝的动作。要把 hook 输出对照基于规则的 permission 来解析。
- **Stop hook 无限循环：**一个 `Stop` hook 可能拦截、触发自我修正，然后又再次触发。要追踪 stop hook 是否已经在运行中。
- **hook 配置在 session 中途改变：**某个进程可能在启动后修改 settings。要对 hook 配置做一次快照。
- **慢速 hook 卡住循环：**hook 可能 shell out 去做很慢的工作。要加上 timeout。
- **PostToolUse 意外停止：**若 post-hook 返回 `preventContinuation`，要把它呈现为一次优雅的停止，而不是崩溃。

---

## 可执行程序

[`src/`](src/) 承接 03 并加上：

- [`hooks.py`](src/hooks.py)：带有 `fire_pre` 与 `fire_post` 的 `Hooks` 对象。
- [`loop.py`](src/loop.py)：`_dispatch` 在 gate 之前触发 `PreToolUse`，在执行之后触发 `PostToolUse`。
- [`test.py`](src/test.py)：一个 pre-hook 即使在 `bypassPermissions` 之下也拦截 `rm -rf`。

```bash
python sections/04-hooks/src/test.py         # offline checks, no key
uv run python sections/04-hooks/src/demo.py  # live demo, needs a key
```

---

## 出处

- Claude Code 源码：`types/hooks.ts`、`entrypoints/sdk/coreTypes.ts`、`services/tools/toolHooks.ts`、`query/stopHooks.ts`、`services/tools/toolExecution.ts`、`setup.ts`。
- learn-claude-code · s04_hooks：section framing。
