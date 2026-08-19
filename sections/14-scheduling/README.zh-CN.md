# 14 · Scheduling

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 让 agent 的 turn 由时钟启动，而不只是由 user 输入启动。

后台工作仍然需要有人或有东西来启动它。很多 task 应该稍后才跑或重复跑：一份报告、一则提醒，或一个定期检查状态的 task。

调度就是先记下什么时候要做什么。时间一到（fire），就把一个 prompt 放进 queue。正常的 loop 会把那个 prompt 当成一个新的 turn 来处理。

调度必须：

1. 把 schedule 存储在单个 turn 之外。
2. 独立于 loop 之外地监视时间。
3. 当 schedule fire 时把一个 prompt 放进 queue。
4. 可选地让 schedule 跨重启后仍存活。

少了这一层，agent 就只能对 user 输入做出反应。

---

## 机制

![机制图](assets/14-scheduling.png)

把时钟和 loop 分开。scheduler 监视时间。它不会直接调用 model。

在 fire 的时刻，scheduler 只把一个 prompt 放进 queue。driver 会等到没有 turn 正在跑的时候（也就是两个 turn 之间）才把 queue 里的 prompt 拿出来，交给处理 user 输入的同一个 agent loop，当成新的一轮跑。

- 一个 schedule 就是数据：要跑的 prompt、一个 fire 时间，以及可选的重复间隔。scheduler 把每一条存成一个 task。
- 一次性（one-shot）的 schedule fire 一次后就把自己删掉。
- 周期性（recurring）的 schedule 会重新装填到下一个间隔。
- 一个 durable 的 schedule 能在重启后存活，但在 host 关机时它不会 fire。
- heartbeat 是一种周期性 schedule，它问的是一个问题。它醒来、看一眼来源，多数时候判断没什么好讲的。

### New: scheduler 与 fire queue

`tick` 检查哪些 task 已经到了预定时间。fire 就是把一个 prompt 放进 queue：

```python
def tick(self):                                       # src/scheduler.py; called by a daemon thread
    now = self._clock()
    for tid, t in list(self._tasks.items()):
        if now >= t["due"]:
            self._pending.put({"prompt": t["prompt"], "channel": t.get("channel")})
            if t["every"]:                            # enqueue, do not run the model here
                t["due"] = now + t["every"]
            else:
                self._tasks.pop(tid, None)
    self._save()                                      # durable tasks only
```

- 时钟是可注入的，所以测试会用一个假时钟。
- `run()` 在一个 daemon thread 上调用 `tick`。
- `_save` 把 durable task 持久化成 JSON。
- 在相同路径上创建一个新的 `Scheduler`，会重新加载 durable task 并接续 id。

### New: 投递答案

调度触发的 turn 跑起来时，屏幕前没有用户，跑完的答案不主动送出去就没人看到。所以每个 task 可以指定一个 channel。
channel 就存在 task 里，是那条调度数据的一个字段：`create(..., channel="console")` 存进去，`tick` fire 时再把它和 prompt 一起放进 queue。
所以 driver 从 queue 拿出来的每个条目，已经是 `{"prompt": ..., "channel": ...}`，不用再去别处查这个答案要送哪。

`deliver` 负责把这个 turn 的答案送到 channel（Hermes 会把 cron 输出投递到该 job 的聊天平台）：

```python
SILENT = "[SILENT]"                              # a fired run may decide nothing is worth sending

def deliver(channels, fired, text) -> bool:      # src/scheduler.py
    if not fired.get("channel") or text.lstrip().startswith(SILENT):
        return False
    channels[fired["channel"]](text)
    return True
```

- `channels` 把 channel 名称对应到一个送信的 callable（这里是 print；真正的 adapter 是第 19 章的事）。
  task 指定 channel；driver 拥有这张对照表。两边互不知道对方的细节。
- 答案以 `[SILENT]` 开头时，`deliver` 直接跳过，不把它送进 channel。这是给调度任务的约定：模型跑完发现没有新东西值得通知用户（例如巡检一切正常），就用这个开头。driver 手上仍有完整文本，要存档照样可以。
- 没有 channel 表示答案留在本地，也就是加入投递之前的行为。
- `bool` 返回值让 driver 可以改走别条路（demo 会打印出未投递的答案），而不是悄悄丢掉答案。

### Heartbeat

有些来源不会主动推送：没有 webhook 的信箱、没有 feed 的网页、你不问就不回答的服务。
对这些来源，能用的触发条件只剩时钟。做法叫 heartbeat：一个周期性的 schedule，prompt 是叫 agent 去看一眼，不是叫它动手。
看一下来源，判断有没有变化值得讲一句，没有就闭嘴。

heartbeat 跑完发现没什么好讲的，就回一个 `[SILENT]`。照上面那条规则，`deliver` 什么都不会送出去。
这一次 tick 只花一次 model 调用，channel 上不会多一则消息，所以这个 schedule 可以跑得比较密。

heartbeat 和 cron 在这里用的是同一组零件：一个 prompt、一个重复间隔、一个 channel。差别只在 prompt。
cron 的 prompt 是下命令，heartbeat 的 prompt 是问问题。

### 如何整合

调度分成两半。`tick` 在自己的 daemon thread 上跑（第 13 章的后台执行），它不碰 model，fire 时只把 prompt 放进 queue：

```python
def run(self):                                        # src/scheduler.py; started by sched.run()
    def loop():
        while not self._stop.wait(self.CHECK_INTERVAL):   # wakes once per second
            self.tick()
    threading.Thread(target=loop, daemon=True).start()    # daemon: never keeps the process alive
```

真正执行 turn 的是前台的 driver：它在两个 turn 之间把 queue 清空，为每个 fire 出来的 task 调用一次 `run_turn`：

```python
for task in sched.drain():                            # src/demo.py · between turns
    messages = [{"role": "user", "content": task["prompt"]}]
    deliver(channels, task, run_turn(messages, model, reg, session))
```

一个 fire 出来的 prompt 会变成一个新的、类似 user 的 turn。它用的是同一套 loop、权限、hook、记忆、context 管理和恢复路径。它的答案会送到该 task 的 channel。

### 延伸阅读

以下设计 `src/` 都没有实现，出自 ai-agent-book，也未经下面表格的系统证实。

**时钟做得到的极限：**heartbeat 只有一个参数要调，就是间隔。它同时决定了账单和最糟情况下的延迟，这两件事会互相拉扯。
间隔短，model 一直醒过来，多半什么也没发现。间隔长，便宜，但消息晚。
换哪个间隔都解不掉。时钟是在采样状态，不是在盯着事件，所以它只知道自己上次是什么时候看的，不知道事情是什么时候发生的。

**能用推送就用推送：**来源如果能主动调用 agent，事情发生的当下就触发，轮询成本归零。
所以顺序是：来源支持推送就用推送，不支持才用 heartbeat，真的跟时间绑在一起的工作（例如周一的报表）才用 cron。
入站推送那一侧由第 19 章负责。

---

## 各系统做法

各个 agent 如何决定何时执行调度工作。

| | Claude Code | Hermes Agent | deepseek-harness |
| --- | --- | --- | --- |
| **Pros** | 简单又私密。durable 的 schedule 能在重启后存活。 | 不需要托管服务，无人看管也能 fire。 | 提醒跟着 session 一起重放。错过的几次会并成一个 turn。 |
| **Cons** | 只在 session 运行时才会 tick，remote trigger 还要托管服务。 | gateway 得一直跑，共享 job store 还要靠锁。 | 只能固定间隔。session 关掉就什么都不会 fire。 |
| **Why** | 假设本地有 session 开着。 | gateway 是 server process，无人看管也能 fire。 | 提醒就是对话状态，所以归 session log 管。 |
| **How: trigger** | Cron、sleep 和 remote trigger，由 ticker 定期检查。 | gateway tick 上的 cron，跟着用户的时区走。 | 延迟多久后、某个时间点，或固定间隔，最快五分钟一次。 |
| **How: durability** | session 状态，或存成一个带锁的 JSON 文件。 | CLI 和 gateway 共享一个 JSON job store，认领是原子的。 | 写进 session log 的事件。fork 保留历史，但不带走提醒。 |
| **How: wakeup** | fire 出来的 prompt 进 queue，在 turn 之间执行。 | 到点的 job 并行跑，输出投递到聊天平台。 | 等 agent 完全闲下来，才排一个 turn。至少送达一次。 |

---

## 哪里会出错

- **重复 fire（Double fire）：**一次很快的 tick 可能在同一个 cron 分钟内匹配到不止一次。追踪上一次 fire 的分钟。
- **许多 schedule 一起 fire：**把每个周期性 task 的时间错开一点。错开量从 task 本身算出来，每次都一样。
- **durable 不等于永远开机：**本地 durable schedule 只能在重启后存活。要离线 fire，改用 remote trigger 或 OS timer。
- **cron 表达式有误（Bad cron expression）：**在 create 时验证，并跳过无效的已加载条目。
- **loop 正忙：**把 prompt 放进 queue，等 turn 之间再拿出来跑。
- **通知疲劳（Alert fatigue）：**heartbeat 每次 tick 都汇报，用户就学会忽略它。让 prompt 自己判断什么值得送出，其余时候闭嘴。
- **两次 tick 之间的事件：**时钟采样的是状态。在两次 tick 之间出现又消失的变化，它看不到。改读 log 或游标，或把来源换成推送。

---

## 可执行程序

[`src/`](src/) 把 13 带了过来，并加上：

- [`scheduler.py`](src/scheduler.py)：一个 scheduler、fire queue、周期性重新装填、一次性删除、durable 的 JSON store，以及 channel 投递（`deliver`、`SILENT`）。
- [`test.py`](src/test.py)：用一个假时钟测试一次性、周期性、重新加载和投递的行为。
- [`demo.py`](src/demo.py)：把一个 prompt 排在一秒后、以一个新 turn 执行它，并把答案投递到 console channel。

loop 没有改变。调度从 loop 之外启动 turn。

```bash
python sections/14-scheduling/src/test.py         # offline checks, no key
uv run python sections/14-scheduling/src/demo.py  # live demo, needs a key
```

---

## 出处

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code)：
  `tools/ScheduleCronTool/`、`tools/RemoteTriggerTool/`、`tools/SleepTool/`、`utils/cronScheduler.ts`、`hooks/useScheduledTasks.ts`、`utils/queueProcessor.ts`。
- [Hermes Agent 源码](https://github.com/NousResearch/hermes-agent)：
  `cron/scheduler.py`（`tick`、`_resolve_cron_disabled_toolsets`）、`cron/jobs.py`（`_jobs_lock`、`claim_dispatch`）、`hermes_time.py`。
- [deepseek-harness source](https://github.com/deepseek-ai/deepseek-harness)（`dsh-v0.1.0-rc.7`）：
  `packages/schedule/schedule/src/runtime.ts`、`packages/schedule/schedule/src/persistence.ts`、`packages/schedule/schedule/src/tools.ts`、
  `docs/subsystems/schedule.md`、`docs/tool-catalog.md`。
- [learn-claude-code · s14_cron_scheduler](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
- [ai-agent-book](https://github.com/bojieli/ai-agent-book)：`book/chapter4.md`，以中文原版为准。
  带判断的 heartbeat 唤醒、通知疲劳，以及时间驱动触发的极限。
