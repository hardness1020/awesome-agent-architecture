# 13 · Background execution

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 把跑很久的工作移出主 loop 去跑，稍后再汇报。

有些操作要花很久：安装、构建、测试套件、记忆整合，或是一个跑着自己 loop 的 subagent。

基本的 agent loop 会等工具调用完成后，才再次调用 model。

对快速的读取来说这没问题。但有些工作跑很久，明明可以让它自己跑，agent 同时做别的事。这种工作让 loop 干等就很浪费。

background execution 必须：

1. 决定哪些操作可以不阻塞地执行。
2. 启动它们，并立刻返回一个 handle。
3. 追踪 running、completed、failed 和 killed 这些状态。
4. 稍后把一则完成消息送回 loop 里。

少了这一层，一个慢指令就能冻结整个 agent。

---

## 机制

![机制图](assets/13-background-execution.png)

这里有三个部件：

1. 一个把工作移出 loop 的 starter，它会返回一个 handle。
2. 一个追踪 task 状态的 runtime。
3. 一个 queue，会在稍后的某个 turn 注入一则完成 notification。

loop 不会停下来等这件工作跑完。

- 后台执行是一个执行选项，而不是一种特殊的工具类型。
- 被放到后台的调用会立刻返回一个正常的 `tool_result`。
- 真正的结果稍后才会用另一则 notification 送进来。
- 一整个 subagent 也可以在后台执行。

### New: 在 loop 外启动工作，把 notification 收进对话

`start` 在一个 worker thread 上跑工作，并返回一个 task id：

```python
def start(self, fn):                                   # src/background.py; returns immediately
    self._next += 1
    tid = self._next
    self._state[tid] = "running"
    def work():
        try:
            self._finish(tid, "completed", str(fn()))  # enqueues a <task_notification>
        except Exception as e:
            self._finish(tid, "failed", f"{type(e).__name__}: {e}")
    threading.Thread(target=work, daemon=True).start()
    return tid
```

`drain_into` 把已完成的 notification 合并到下一个 user turn：

```python
def drain_into(messages, runtime):                     # src/background.py
    notes = runtime.drain() if runtime else []
    if notes and messages and isinstance(messages[-1].get("content"), str):
        messages[-1]["content"] = "\n".join(notes) + "\n\n" + messages[-1]["content"]
```

`backgroundable` 包装任何工具，并在它的 schema 加上 `run_in_background`：

```python
def backgroundable(tool, runtime):                     # src/background.py; wraps ANY tool
    def run(a):
        if a.get("run_in_background"):
            inner = {k: v for k, v in a.items() if k != "run_in_background"}
            tid = runtime.start(lambda: tool.run(inner))
            return f"started background task {tid} ({tool.name}); ..."
        return tool.run(a)
    ...
    return replace(tool, run=run, ...)
```

### 如何整合

loop 在一个 turn 开始时，把 queue 里累积的完成 notification 收进对话：

```python
background.drain_into(messages, runtime)               # src/loop.py
```

"一个工具调用对一个工具结果"的规则依然成立。一则迟来的完成 notification，不是给旧 `tool_use_id` 的延迟 `tool_result`。它是一则全新的 notification 消息。

---

## 各系统做法

各个 agent 如何把工作移出 loop，又如何汇报完成。

| | Claude Code |
| --- | --- |
| **Pros** | 吞吐量提升，也不再有空闲的等待。连单纯的等待都是非阻塞的，不会占住一个 shell process。 |
| **Cons** | 结果可能较晚抵达，顺序也可能颠倒。runtime 需要 task 状态、notification 和清理机制。 |
| **Why** | 一个跑很久的指令不该冻结整个 agent。这种工作可以趁 agent 做别的事时继续跑。 |
| **How: off-loop primitive** | 后台 shell task 和后台 agent task，连记忆整合都用这种方式跑。subprocess 会继续执行，输出被重定向。 |
| **How: notification** | 一则 `<task_notification>` 消息。完成消息走同一个共享 queue，runtime 会追踪每个 task 的状态。 |
| **How: re-entry** | notification 在 turn 之间从 queue 收进对话，分 `now`、`next`、`later` 三种优先级。 |

---

## 哪里会出错

- **交互式提示卡住（Interactive prompt stalls）：**某个后台指令在等输入。检测像提示的输出，并通知 model 去 kill 它，或以非交互方式重跑。
- **完成消息丢失（Lost completion）：**某个完成的 task 从没抵达 loop。让完成消息走同一个共享 queue，并把 task 标记为已通知。
- **配对错误的 notification（Mispaired notification）：**重用旧的 `tool_use_id` 会弄坏 transcript。改用独立的 notification 文字。
- **并发太多（Too much concurrency）：**太多后台 task 会耗尽资源。加上 kill 路径和上限。
- **退出时的 process 泄漏（Process leak on exit）：**后台工作可能活得比 session 还久。注册清理机制。

---

## 可执行程序

[`src/`](src/) 把 12 带了过来，并加上：

- [`background.py`](src/background.py)：一个 runtime、notification queue、`drain_into`，以及 `backgroundable`。
- [`loop.py`](src/loop.py)：在调用 model 前，把待处理的 notification 收进对话。
- [`test.py`](src/test.py)：检查 start、failure、drain，以及后台 subagent。
- [`demo.py`](src/demo.py)：在后台启动一个 subagent，稍后再读取它的结果。

```bash
python sections/13-background-execution/src/test.py         # offline checks, no key
uv run python sections/13-background-execution/src/demo.py  # live demo, needs a key
```

---

## 出处

- [Claude Code task sources](https://github.com/yasasbanukaofficial/claude-code)：`tasks/LocalShellTask/`、`tasks/DreamTask/`。
- [Claude Code tool and queue sources](https://github.com/yasasbanukaofficial/claude-code)：`tools/BashTool/BashTool.tsx`、`tools/SleepTool/prompt.ts`、`utils/task/framework.ts`、`utils/messageQueueManager.ts`。
- [learn-claude-code · s13_background_tasks](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
