# 14 · Scheduling

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> Start agent turns from a clock, not only from user input.

Background work still needs someone or something to start it. Many tasks should run later or repeat: a report, a reminder, or a polling task.

Scheduling stores a future trigger. When it fires, it enqueues a prompt. The normal loop handles that prompt as a new turn.

Scheduling must:

1. Store a schedule outside one turn.
2. Watch time independently of the loop.
3. Enqueue a prompt when the schedule fires.
4. Optionally persist schedules across restarts.

Without this layer, the agent can only react to user input.

---

## Mechanism

![Mechanism diagram](assets/14-scheduling.png)

Separate the clock from the loop. The scheduler watches time. It does not call the model directly.

At fire time, the scheduler only enqueues a prompt. The driver drains the queue between turns, when no turn is in flight, and runs each prompt through the same agent loop that handles user input.

- A schedule is data: a prompt to run, a fire time, and an optional repeat interval. The scheduler stores each one as a task.
- A one-shot fires once and then deletes itself.
- A recurring schedule re-arms to the next interval.
- A durable schedule survives restart, but it does not fire while the host is off.

### New: the scheduler and fire queue

`tick` checks due tasks. Firing means enqueueing a prompt:

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

- The clock is injectable, so tests use a fake clock.
- `run()` calls `tick` on a daemon thread.
- `_save` persists durable tasks to JSON.
- A new `Scheduler` on the same path reloads durable tasks and resumes ids.

### New: delivering the answer

A fired run has no human waiting, so the answer needs a route out. Each task can name a channel.
The channel is a field on the task: `create(..., channel="console")` stores it, and `tick` enqueues it with the prompt.
Each drained item is already `{"prompt": ..., "channel": ...}`, so the driver never looks up where an answer goes.

`deliver` routes the turn's answer (Hermes delivers cron output to the job's chat platform):

```python
SILENT = "[SILENT]"                              # a fired run may decide nothing is worth sending

def deliver(channels, fired, text) -> bool:      # src/scheduler.py
    if not fired.get("channel") or text.lstrip().startswith(SILENT):
        return False
    channels[fired["channel"]](text)
    return True
```

- `channels` maps a channel name to a send callable (print here; a real adapter is section 19's job).
  The task names the channel; the driver owns the map. Neither knows the other's details.
- When the answer starts with `[SILENT]`, `deliver` skips the channel send. This is the convention for a scheduled check that found nothing worth telling the user (a poll that saw no change). The driver still holds the full text and can log it.
- No channel means the answer stays local, the pre-delivery behavior.
- The `bool` return lets the driver fall back (the demo prints undelivered answers) instead of losing the answer silently.

### How it integrates

Scheduling is two halves. `tick` runs on its own daemon thread (section 13's background execution); it never touches the model and only enqueues on fire:

```python
def run(self):                                        # src/scheduler.py; started by sched.run()
    def loop():
        while not self._stop.wait(self.CHECK_INTERVAL):   # wakes once per second
            self.tick()
    threading.Thread(target=loop, daemon=True).start()    # daemon: never keeps the process alive
```

The turn itself runs in the foreground: the driver drains the queue between turns and calls `run_turn` once per fired task:

```python
for task in sched.drain():                            # src/demo.py · between turns
    messages = [{"role": "user", "content": task["prompt"]}]
    deliver(channels, task, run_turn(messages, model, reg, session))
```

A fired prompt becomes a new user-style turn. It uses the same loop, permissions, hooks, memory, context management, and recovery paths. Its answer routes to the task's channel.

---

## Per system

How each agent decides when to run scheduled work.

| System | Trigger | Durability | Wakeup |
| --- | --- | --- | --- |
| **Claude Code** | Cron, sleep, and remote triggers. | Session or durable local schedules. | Fired prompts enter the queue. |
| **Hermes Agent** | Cron expressions on a gateway tick. | JSON job store with cross-process locks. | Job output delivers to a chat platform. |

### Claude Code

- `CronCreate`, `CronList`, and `CronDelete` manage cron entries.
- A cron entry stores `id`, `cron`, `prompt`, `recurring`, and `durable`.
- `cronScheduler.ts` ticks on an interval and calls `onFire(prompt)`.
- `useScheduledTasks.ts` enqueues fired prompts at `priority: 'later'`.
- The queue drains when no turn is in flight.
- `durable: true` writes `.claude/scheduled_tasks.json`.
- A lock prevents multiple open sessions from firing the same file-backed schedule.
- `RemoteTriggerTool` uses a hosted trigger so work can fire without a local process.

### Hermes Agent

- The gateway is a server process, so durable schedules fire unattended without a hosted trigger.
- `cron/scheduler.py` `tick()` runs on a gateway thread. Due jobs spawn agent runs in parallel threads.
- Jobs persist in `~/.hermes/cron/jobs.json`. `_jobs_lock()` combines a thread lock with fcntl or msvcrt file locks so the CLI and the gateway do not clobber each other.
- `claim_dispatch` claims a due job atomically, preventing double fire across processes.
- Cron runs get restricted toolsets: `_resolve_cron_disabled_toolsets` always disables `cronjob`, `messaging`, and `clarify`, then layers user config on top.
- Output saves to `~/.hermes/cron/output/<job_id>/` and delivers to the job's routed platform and channel.
- A `[SILENT]` token in the output suppresses chat delivery. The output file still saves.
- Heartbeat and last-success files let `hermes cron status` tell a dead ticker from a live but failing one.
- `hermes_time.now()` resolves a configured IANA timezone, so schedules follow the user's clock, not the server's.

> **Trade-off:** Local schedules are simple and private, but they only tick while the process runs. Remote triggers can fire unattended, but they require a hosted service and auth.

---

## Failure modes

- **Double fire.** A fast tick can match the same cron minute more than once. Track the last fired minute.
- **Many schedules fire together.** Add deterministic jitter to recurring tasks.
- **Durable means always-on.** Local durable schedules only survive restart. Use remote triggers or an OS timer for offline firing.
- **Bad cron expression.** Validate on create and skip invalid loaded entries.
- **Loop is busy.** Enqueue the prompt and drain it between turns.

---

## Runnable

[`src/`](src/) carries 13 forward and adds:

- [`scheduler.py`](src/scheduler.py): a scheduler, fire queue, recurring re-arm, one-shot delete, durable JSON store, and channel delivery (`deliver`, `SILENT`).
- [`test.py`](src/test.py): uses a fake clock to test one-shot, recurring, reload, and delivery behavior.
- [`demo.py`](src/demo.py): schedules a prompt one second out, runs it as a new turn, and delivers the answer to a console channel.

The loop is unchanged. Scheduling starts turns from outside it.

```bash
python sections/14-scheduling/src/test.py         # offline checks, no key
uv run python sections/14-scheduling/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `tools/ScheduleCronTool/`, `tools/RemoteTriggerTool/`, `tools/SleepTool/`, `utils/cronScheduler.ts`, `hooks/useScheduledTasks.ts`, `utils/queueProcessor.ts`.
- Hermes Agent source: `cron/scheduler.py` (`tick`, `_resolve_cron_disabled_toolsets`), `cron/jobs.py` (`_jobs_lock`, `claim_dispatch`), `hermes_time.py`.
- learn-claude-code · s14_cron_scheduler: section framing.
