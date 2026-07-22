# 12 · Task system

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 把工作以持久的 task 形式存储，并带有依赖关系。

第 5 章的 todo list 只放在内存里，process 一结束就消失。它也没办法规定哪个工作要等哪个先完成。

task system 把工作以记录的形式存到磁盘上。每条记录都可以带有依赖关系。当阻挡条件完成后，worker 才能认领 task。

task system 必须：

1. 把每个工作单元存成持久的对象。
2. 用数据来表示顺序。
3. 在跨 turn、跨 session、甚至宕机后都能存活。
4. 让一个 task 只被一个 worker 认领。

少了这一层，计划就只存在于当前的 context window 里。

---

## 机制

![机制图](assets/12-task-system.png)

一个 task 就是磁盘上的一条 JSON 记录。`blockedBy` 和 `blocks` 这两个字段记着它跟其他 task 的先后关系。worker 认领 task 前要先拿到一把 file lock，所以一次只有一个 worker 在认领。

- ID 是连续的，而且永不重复使用。
- create、get、update、list 都是单纯的 CRUD。
- `claim` 是那道关卡。它在指派 owner 之前，会先检查 ownership 和阻挡条件。
- 磁盘上的图存储整个计划。另一个 runtime 可以追踪正在进行的后台执行工作。

### New: task store 与 claim 关卡

`create` 会配置一个 id 并写入一条 task：

```python
def create(self, subject, blocked_by=()):              # src/tasks.py
    tid = self._next_id()
    task = {"id": tid, "subject": subject, "status": "pending",
            "owner": None, "blockedBy": list(blocked_by), "blocks": []}
    self._write(task)
    ...                                                # keep the reverse `blocks` edge in sync
    return task
```

`claim` 有加锁。这让「先检查再设置」在多个 worker 之间也安全：

```python
def claim(self, tid, owner):                           # src/tasks.py
    with self._lock():                                 # fcntl.flock, exclusive
        task = self.get(tid)
        if task["owner"] is not None:
            return {"ok": False, "reason": "already_claimed"}
        unmet = [b for b in task["blockedBy"]
                 if (self.get(b) or {}).get("status") != "completed"]
        if unmet:
            return {"ok": False, "reason": "blocked"}
        task["owner"], task["status"] = owner, "in_progress"
        self._write(task)
        return {"ok": True, "task": task}
```

### 如何整合

task 工具只是 store 之上的一层薄包装：

```python
for t in task_tools(TaskStore(dir)):                   # src/demo.py
    reg.register(t)                                    # TaskCreate / TaskUpdate / TaskGet / TaskList
```

loop 没有改变。model 就像调用其他任何工具一样，调用 `TaskCreate`、`TaskUpdate`、`TaskGet` 和 `TaskList`。

---

## 各系统做法

持久的 task 图如何塑形，又如何推进。

| | Claude Code |
| --- | --- |
| **Pros** | 以文件为后盾的 task 能在宕机后存活，也支持多个 worker。 |
| **Cons** | 代价是文件系统的读、写和锁。记录也要验证，避免依赖关系指到不存在的 task，或互相等待。 |
| **Why** | 放在内存里的 todo list 会跟着 process 一起消失。计划必须撑过 session 和宕机，顺序也要用数据来表示。 |
| **How: task record** | 每个 task 一个 JSON 文件。字段涵盖 id、subject、status、owner，以及依赖关系的边。 |
| **How: dependencies** | `blockedBy` 和 `blocks` 两种边。可以直接建立被阻挡的 task。阻挡条件全部完成前，认领会被拒绝。 |
| **How: persistence** | 每个 task 一个文件，外加一个 high-water mark 记录已发出的最大 id。一个开关决定要不要用持久 task 取代 in-memory todo。 |
| **How: lifecycle** | `pending -> in_progress -> completed`。一把 file lock 让认领动作序列化。teammate 离开时会清掉 ownership。 |

---

## 哪里会出错

- **依赖 loop（Dependency cycle）：**两个 task 可能互相阻挡。让图保持无环，或加上 loop 检查。
- **认领竞态（Claim race）：**两个 agent 可能抢同一个 task。把认领路径加锁。
- **卡在 in_progress 的孤儿 task：**worker 可能在认领后死掉。在 worker 离开时清掉 ownership。
- **无效记录（Invalid record）：**手动编辑或旧版的文件可能不符合 schema。安全地解析，并跳过坏掉的记录。
- **持久系统被关闭：**in-memory todo 仍可能丢失。对必须存活的工作，改用以磁盘为后盾的 task。

---

## 可执行程序

[`src/`](src/) 把 11 带了过来，并加上：

- [`tasks.py`](src/tasks.py)：一个以磁盘为后盾的 `TaskStore`、claim 关卡，以及 `Task*` 工具。
- [`test.py`](src/test.py)：检查依赖关系、认领关卡，以及一场 10-agent 的认领竞态。
- [`demo.py`](src/demo.py)：把一个三个 task 的计划持久化成 JSON 文件。

```bash
python sections/12-task-system/src/test.py         # offline checks, no key
uv run python sections/12-task-system/src/demo.py  # live demo, needs a key
```

---

## 来源

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code)：`utils/tasks.ts`、`Task.ts`，以及 `Task*Tool/` 目录。
- [learn-claude-code · s12_task_system](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
