# 16 · Coordination

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> lead 依任務規模組出一個團隊，把隊友各自 spawn 到獨立的 thread 上，大家透過共用的 inbox 交談。

一個 agent 只有一個 context window 和一條進行中的工作線。大型任務通常需要多個 agent 同時運作。

subagent 可以處理聚焦的任務，但一次性的 subagent 一旦啟動就很難再引導。

要協調的 agent 需要一種方式互相 spawn、需要穩定的名字、需要 inbox 來交談，還需要一種方式把權限請求送回給人類。

協調必須：

1. 給 agent 穩定的位址。
2. 讓 lead 依任務規模組出團隊。
3. 讓 lead 把每個隊友 spawn 到各自的 thread 上。
4. 讓每個隊友自己拉取 inbox 並行動，不必靠腳本驅動。
5. 把有閘門的動作往上冒泡給人類審核者。

沒有這一層，大型工作要嘛維持序列進行，要嘛拆成無法協作的 worker。

---

## 機制

每個 agent 擁有一個 inbox。送出訊息就是寫入收件者的 inbox。投遞發生在收件者清空自己的 inbox 時。

團隊名單是 lead 的選擇，不是腳本的。lead 呼叫 `TeamCreate` 依任務決定團隊規模與組成，接著 spawn 每一位成員。

lead 不會親手啟動隊友。它呼叫 `SpawnTeammate`，由 harness 在背景 thread 上跑隊友的 loop（第 13 章）。
隊友接著拉取自己的 inbox 並行動，所以腳本不驅動任何人。

demo 裡沒有中央 broker。有的是名字、inbox 路徑與訊息形狀的共用慣例。

```mermaid
flowchart LR
    L([Lead]) -->|TeamCreate| R[(Team roster)]
    L -->|SpawnTeammate| T[Worker loop · serve_mailbox]
    L -->|SendMessage| WI[Worker inbox]
    T -->|pull| WI
    T -->|reply| LI[Lead inbox]
    T -.->|permission_request| LI
    LI -.->|route to UI| H([Human approves])
    H -.->|verdict| T
```

- 每個 agent 擁有一個 inbox。
- 一則訊息有 sender、recipient 和 content。
- lead 呼叫 `TeamCreate` 決定名單的規模與組成；`SpawnTeammate` 再啟動每位成員。
- lead 用 `SpawnTeammate` spawn 一個隊友；那個隊友在自己的 thread 上運作。
- `to="*"` 會 broadcast 給除了 sender 以外的每一位隊友。
- sender 寫完就返回。它們不會 block 等待回覆。
- 隊友每次輪詢都拉取自己的 inbox，並把新訊息折進下一個 turn。
- 權限請求走同一個管道。

### New: 組出團隊

`TeamCreate` 是 lead 呼叫來決定名單規模與組成的工具。它填入一個單槽的 holder，harness 在 spawn 每位成員時讀回：

```python
def team_tools(root, me, formed):                      # src/mailbox.py
    def create(a):
        members = list(dict.fromkeys([me, *a["members"]]))   # the lead joins its own team
        formed["team"] = Team(root, members)                 # the tool call sizes and forms the team
        return f"team created: {', '.join(members)}"
    ...                                                # SendMessage stays inert until the team exists
```

- 腳本既不固定規模也不固定名字；兩者都由 lead 依任務挑選。
- `SendMessage` 在 `TeamCreate` 執行前是無作用的，所以 lead 得先組出團隊才能對它說話。
- `formed` 是一個單槽的 holder（ponytail：一個 in-process 的團隊登記表替身；可以用一個名單檔案作為後端，讓另一個 process 的隊友加入）。

### New: spawn 一個隊友

`SpawnTeammate` 是 lead 的模型呼叫的工具。harness 在第 13 章的 runtime 上、在自己的 thread 上啟動隊友的 loop：

```python
def teammate_tools(runtime, spawn_worker):             # src/mailbox.py
    def spawn(a):
        runtime.start(lambda: spawn_worker(a["name"]))  # section-13 thread runs the teammate's loop
        return f"spawned teammate {a['name']}; it runs on its own thread and pulls its own work"
    return [Tool("SpawnTeammate", spawn, is_read_only=True, ...)]
```

隊友的 loop 是 `serve_mailbox`：拉取 inbox、行動、重複。它在被 spawn 出來的 thread 上運作，所以隊友是自己反應，不是靠腳本：

```python
def serve_mailbox(team, me, work, *, poll=0.05, max_idle_polls=None):   # src/mailbox.py
    while True:
        chat = [m for m in team.drain(me) if isinstance(m["content"], str)]
        if chat:                                        # a message to act on
            folded = "\n".join(f"<message from={m['from']!r}>{m['content']}</message>" for m in chat)
            work(folded)                                # one inner loop (section 1) on the message
            continue
        time.sleep(poll)                                # empty: poll again
```

- `spawn_worker(name)` 是應用端的 thunk；它為那個隊友跑一個 `serve_mailbox` loop。
- 隊友在 drain 時就消耗訊息，所以一則訊息只投遞一次。
- 目前還沒有優雅的停止方式。thread 是一個 daemon，會隨 process 一起死掉。第 17 章加入 shutdown handshake。
- `max_idle_polls` 為閒置等待設上界，好讓 demo 或 test 結束；真正的隊友會一直輪詢，直到 process 停止。

### inbox 與權限管道

`mailbox.py` 實作一個由具名 inbox 組成的 `Team`：

```python
def send(self, frm, to, content):                      # src/mailbox.py
    targets = [m for m in self.members if m != frm] if to == "*" else [self._check(to)]
    with self._lock():                                 # serialize concurrent senders
        for t in targets:
            inbox = self._read(t)
            inbox.append({"from": frm, "to": t, "content": content})
            self._path(t).write_text(json.dumps(inbox))
```

- `_check` 在未知名稱變成路徑之前就拒絕它。
- lock 把 read-modify-write 序列化，所以並行的 sender 不會漏掉訊息。
- `drain` 讀取並清空一個 inbox。

permission bubbling 是一種 approver 的實作。它把有閘門的呼叫透過同一個管道搬給人類：

```python
def bubbling_approver(team, me, lead, human):           # approver for an agent with no human UI
    def approve(name, args):
        team.send(me, lead, {"kind": "permission_request", "tool": name, "args": args})
        verdict = human(name, args)                     # the lead routes it to its approval UI
        team.send(lead, me, {"kind": "permission_response", "tool": name, "ok": verdict})
        resp = [m["content"] for m in team.drain(me)
                if isinstance(m["content"], dict) and m["content"].get("kind") == "permission_response"]
        return bool(resp and resp[-1]["ok"])
    return approve
```

1. 隊友碰到一個有閘門的工具呼叫，但它自己的 loop 前面沒有坐著人類。
2. approver 把一則 `permission_request` 送到 lead 的 inbox。
3. lead 把它導向自己的審核 UI（這裡是 `human` callback）。
4. 裁決以 `permission_response` 的形式回到隊友的 inbox。
5. 隊友讀取那則回覆，把 allow 或 deny 回傳給閘門。

閘門仍然呼叫 `approver(name, args)`，沒有改變。答案以 inbox 訊息而非直接呼叫的形式抵達，所以升級重用了同一個管道。

### How it integrates

demo 跑一個主 agent。lead 走一步，隊友就自己運作起來：

```python
def spawn_worker(name, formed, model):                 # src/demo.py, module level
    team = formed["team"]                              # whatever the lead formed with TeamCreate
    ...                                                 # build the teammate's tools
    return mailbox.serve_mailbox(team, name, work)      # the teammate pulls its own inbox

run_turn([...goal...], model, lead_reg, session)        # the one agent call in demo(): the lead
```

- 唯一由腳本給的輸入是 lead 的目標。lead 用 `TeamCreate` 決定團隊規模、用 `SpawnTeammate` spawn 每一位、用 `SendMessage` 委派。
- `demo()` 跑一個 `run_turn`，也就是 lead 的。隊友自己的 `run_turn` 位於 `spawn_worker`，只能透過 spawn 工具抵達。
- 每個隊友在第 13 章的 thread 上跑 `serve_mailbox`：拉取 inbox、工作、回覆。回覆數量由 lead 決定；主 process 只是等待。
- `loop.py` 維持通用。折疊與拉取 loop 屬於協調，在這個 wrapper 裡完成，不在 `run_turn` 內部。
- 權限閘門沒有改變；有閘門的呼叫仍會冒泡給 lead。

> **接下來：** 這裡的隊友是一個沒有優雅停止方式的 daemon，而且它只對訊息做反應。
> 第 17 章加入 shutdown handshake，好讓 lead 能乾淨地結束一個隊友。
> 第 18 章加入一塊共用的 task 看板，讓閒置的隊友自己認領工作，而不是等著被傳訊息。

---

## 各系統做法

一種設計如何 spawn 出協作的 agent 並把工作分散給它們。

| System | Teammates | Channel | Shared memory | Permission bubbling |
| --- | --- | --- | --- | --- |
| **Claude Code** | in-process 或 remote；各自跑自己的 loop。 | inbox 訊息，memory 或 disk。 | team task list 與 memory dir。 | remote 請求導向本地 UI。 |

### Claude Code

- `TeamCreateTool` 建立一個團隊。`TeamDeleteTool` 移除它。
- lead spawn 一個 `InProcessTeammateTask` 或一個 `RemoteAgentTask`；每個隊友跑自己的 loop。
- in-process 隊友輪詢自己的 inbox（`utils/mailbox.ts`）並在 turn 之間折入訊息。
- `SendMessageTool` 寫入一個 inbox。
- 跨 process 的隊友使用位於 `~/.claude/teams/{team}/inboxes/` 底下的檔案 inbox，搭配 `proper-lockfile`。
- `to: "*"` 會 broadcast。
- 一個團隊擁有一份 task list。團隊 memory 位於 `memdir/teamMemPaths.ts`。
- `remotePermissionBridge.ts` 把 remote 權限請求轉成本地的審核提示。
- coordinator 模式會清空 inbox 並在 turn 之間折入訊息。

> **取捨：** 檔案 inbox 具耐久性，並能跨越 process 或機器邊界。它們增加輪詢與 lock 成本。in-memory inbox 快，但會隨 process 一起死掉。

---

## 失效模式

- **遺失訊息的競態。** 兩個 sender 同時寫一個 inbox。用 lock 保護 read-modify-write。
- **對等 deadlock。** agent 互相等待。把訊息排入佇列並在 turn 之間 drain，而不是用會 block 的傳送。
- **權限卡住。** 隊友沒有人類 UI。把請求冒泡給 lead。
- **create 之前就 spawn。** lead 在 `TeamCreate` 之前就 spawn 或傳訊息，於是沒有名單。讓兩者在團隊存在之前都保持無作用。
- **孤兒隊友。** 被 spawn 的隊友在工作做完後還一直輪詢。為閒置等待設上界，或用第 17 章的 handshake 停止它。
- **含糊的跨 agent 訊息。** 隊友看不到 lead 的對話。讓訊息自成一體。
- **把 chat 當 memory 用。** 耐久的共用事實屬於 team memory。

---

## 可執行程式

[`src/`](src/) 承接第 15 章並加上：

- [`mailbox.py`](src/mailbox.py)：具 locking 的具名 inbox、折疊、`serve_mailbox` loop、bubbling，以及 `TeamCreate`、`SendMessage`、`SpawnTeammate` 這些工具。
- [`test.py`](src/test.py)：檢查定址、broadcast、並行傳送、折疊、bubbling、mailbox loop，以及 `TeamCreate`、`SendMessage`、`SpawnTeammate` 這些工具。
- [`demo.py`](src/demo.py)：lead 走一步（`TeamCreate`、`SpawnTeammate`、`SendMessage`）；每個隊友拉取自己的 inbox、跑一個有閘門的 shell 任務，然後回報。

loop 與 subagent 路徑不變。協調透過 spawn 隊友、drain inbox、傳入一個 approver 來包住 turn。

```bash
python sections/16-coordination/src/test.py         # offline checks, no key
uv run python sections/16-coordination/src/demo.py  # live demo, needs a key
```

---

## 出處

- Claude Code 工具與 inbox：`tools/SendMessageTool/`、`tools/TeamCreateTool/`、`utils/mailbox.ts`、`utils/teammateMailbox.ts`。
- Claude Code 隊友：`tasks/InProcessTeammateTask/`、`tasks/RemoteAgentTask/`、`remote/remotePermissionBridge.ts`、`memdir/teamMemPaths.ts`。
- learn-claude-code · s15_agent_teams：章節框架。
