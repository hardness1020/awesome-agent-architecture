# 18 · Autonomy

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 在沒有使用者 prompt 的情況下跑 loop：閒置時掃描看板，認領一個就緒的 task，然後動工。

自主（autonomy）就是第 1 章的 agent loop，在沒有使用者 prompt 觸發每一輪的情況下持續運轉。

要 spawn 一支團隊，最直覺的設計是有一位 lead 把下一個 task 逐一交給每個 worker。

但這樣無法擴展。十個尚未認領的 task 就意味著十次手動指派，lead 也因此成為瓶頸。

一個 worker 一做完就閒置，也浪費了它剛載入的 context。

解法是自我組織，而不是集中指派。

集中指派也是一種真實可行的設計，而且多數已發表的 multi-agent 研究講的都是它。
在 manager 模式裡，每個子 agent 都註冊成一個 tool，由一位 manager 把每個 subtask 發出去。
manager 手上有完整的計畫，所以它能排順序、砍掉重複的 task，也能提早收工。
代價是每個 task 它都要經手兩次：一次發出去，一次收結果。
兩種設計付的代價不一樣。manager 給你一份全域排序，但每個 task 都得等它排到。
看板給你吞吐量，但得靠 lock，因為認領會過期。這一章走的是看板這條路。

自主機制必須讓一個閒置的 agent 能夠：

1. 察覺自己沒事可做（work 階段已抵達 `end_turn`）。
2. 查看共享看板，找出無人擁有、也沒有被阻擋的 task。
3. 認領其中一個，且不與其他閒置 agent 相互競爭。
4. 針對認領到的 task 重新進入 loop，並持續重複直到看板清空。

少了這一環，每個 agent 都是傀儡。它必須等待使用者或 lead 推來下一個 prompt，於是吞吐量被卡在派工那一端出 prompt 的速度上。

---

## 機制

![機制圖](assets/18-autonomy.png)

一個 outer loop 包住 agent loop。

inner loop 就是第 1 章那個普通的 `while`。當它抵達 `end_turn` 時，agent 不會回傳，而是進入 poll。

poll 會把兩個 channel 裡的東西都收進來：一個定向的 inbox（第 16 章），承接寄給這個 agent 的訊息；一個非定向的看板（第 12 章），放著任何閒置 agent 都能認領的 task。

它依優先序檢查這些來源：先看 shutdown 請求，再看 inbox 訊息，最後才看看板上的 task。

無論找到什麼，都會成為下一個 prompt，接著 inner loop 再跑一次。

- inner loop 依模型的 `stop_reason` 結束，這與第 1 章是同一個訊號。
- poll 先檢查 shutdown，所以停止指令永遠不會被 peer 訊息淹沒。
- 認領是在 lock 之下做「讀取、檢查、再寫入」：挑一個無人擁有、未被阻擋的 task，然後在別的 agent 出手前寫入擁有權。
- 只有當一個 task 的相依項全都 `completed` 時它才可被認領，所以沒有 agent 會認領被阻擋的工作。

shutdown 請求與其確認就是第 17 章的 protocol，所以停止走的是 handshake，不是強制中止。

### New: 閒置 poll

`autonomy.py` 加上 outer loop 與一次 poll pass。`next_action` 把 inbox 收完一次，然後依優先序回傳它找到的第一樣東西：

```python
def next_action(proto, team, store, me):               # src/autonomy.py
    inbox = team.drain(me)
    shutdown = next((m for m in inbox if _is(m, "shutdown_request")), None)
    if shutdown is not None:                            # checked first, so chat cannot starve a stop
        proto.reply(shutdown, "shutdown_approved")
        return ("shutdown", shutdown["content"].get("reason"))
    chat = [m for m in inbox if isinstance(m["content"], str)]
    if chat:
        chat.sort(key=lambda m: m["from"] != "lead")   # lead before peers; sort is stable
        return ("message", _fold(chat))                # section 16's shared fold helper
    task = claim_next(store, me)                        # else claim the next ready task
    return ("task", task) if task is not None else None
```

- 它會回傳三者中最先出現的：shutdown（確認後停止）、折疊後的 chat，或一個認領到的 task。
- shutdown 在 chat 之前檢查，所以 peer 流量無法餓死一次停止（第 16 章）。
- `claim_next` 認領第一個 pending、無人擁有的 task；`TaskStore.claim` 會拒絕被阻擋的工作，並把認領序列化（第 12 章）。
- `None` 代表閒置：outer loop 睡一下再 poll 一次。

### 在 lock 之下認領

poll 提議一個 task；lock 決定誰拿到它。`claim_next` 由舊到新掃描看板，並提議第一個無人擁有、pending 的 task：

```python
def claim_next(store, me):                             # src/autonomy.py
    for t in store.list():                             # oldest first
        if t["status"] == "pending" and t["owner"] is None:
            got = store.claim(t["id"], me)             # read, check, write under a lock
            if got["ok"]:
                return got["task"]
            # not ok: another agent won it, or it just became blocked; try the next
    return None
```

`claim_next` 裡的檢查只是一個提示：兩個閒置 agent 可能同時把同一個 task 讀成無人擁有。`TaskStore.claim`（第 12 章）在 lock 之下做出裁決：

```python
def claim(self, tid, owner):                           # src/tasks.py, section 12
    with self._lock():                                 # fcntl.flock: one claimer at a time
        task = self.get(tid)
        if task["owner"] is not None:                  # someone already won: back off
            return {"ok": False, "reason": "already_claimed"}
        unmet = [b for b in task["blockedBy"]
                 if (self.get(b) or {}).get("status") != "completed"]
        if unmet:                                       # a dependency is not done yet
            return {"ok": False, "reason": "blocked"}
        task["owner"], task["status"] = owner, "in_progress"
        self._write(task)
        return {"ok": True, "task": task}
```

- lock 把讀取、檢查、寫入包成一步做完，中間插不進別的 agent，所以檢查不會在寫入前過時。
- 落敗者在 lock 內重新讀取，看到 `owner` 已被設定，於是拿到 `already_claimed`；`claim_next` 便移到下一個 task。
- 被阻擋的 task 在這裡同樣會被拒絕，所以沒有 agent 會認領相依項尚未 `completed` 的工作。
- 這是唯一一處兩條執行緒爭用共享狀態的地方。poll 的其餘部分都是本地的。

### 如何整合

outer loop 從外部包住 `run_turn`，所以 loop 與 subagent 路徑都不變：

```python
def run_teammate(team, store, me, lead, work):         # src/autonomy.py
    proto, prompt, claimed = Protocol(team, me), None, None
    while True:
        if prompt is not None:
            work(prompt, claimed)                      # inner loop (section 1) does the claimed task
            prompt, claimed = None, None
            team.send(me, lead, {"type": "idle", "reason": "available"})
        action = next_action(proto, team, store, me)   # poll: shutdown, message, or task
        if action is None:                             # idle: sleep, then poll again
            time.sleep(POLL_INTERVAL); continue
        kind, payload = action
        if kind == "shutdown":
            return "shutdown"
        if kind == "task":
            prompt, claimed = task_prompt(payload), payload
        else:
            prompt = payload
```

- 這個 `run_teammate` 就是第 17 章的版本，只多一個 poll 來源：task 看板。shutdown（第 17 章）與 chat（第 16 章）都不變。
- `work(prompt, claimed)` 針對認領到的 task 跑一次 inner loop 到 `end_turn`，接著 agent 宣告自己有空。
- 認領到的 task 成為下一個 prompt。當 poll 找不到任何東西時，worker 自己決定何時停止。
- 那個停止有兩種模式：閒置直到完成 shutdown handshake（第 17 章），或在有限看板上跑滿一定次數的空 poll 後收工。
- 這裡只跑一個 worker，但 loop 是每個 agent 各一份。真正的團隊會同時跑一個 lead loop 與多個 worker loop，共用同一組看板與 inbox。
- lead 只做一個主動步驟：它呼叫工具建立團隊與工作，然後就結束了。
- `TeamCreate` 與 `SpawnTeammate` 是第 16 章的工具；`TaskCreate` 把 task 貼上看板（第 12 章）。
- `SpawnTeammate` 就是 `runtime.start(...)`（第 13 章）：lead 的工具呼叫會在一條執行緒上啟動一個 worker 的自主 loop。
- spawn 之後，拉取工作與決定何時停止都是每個 worker 自己的事，lead 和外層程式都不介入。主行程只是等待 worker 收工。
- 組建團隊、spawn、貼看板都是模型的決定（第 16 章與第 12 章）；自主認領則是第 18 章新增的部分。

### 延伸閱讀

底下這兩套設計，這一章的可執行程式並沒有實作。它們來自 ai-agent-book 對線上 agent 的描述，以及已發表的研究。
它們也不是下面表格那些系統確定的行為。把它們當成可以試試看的設計就好。

**怎麼問一個正在忙的 worker：**poll 只告訴 worker 下一步做什麼，它從來不會告訴 lead 某個正在跑的 worker 現在怎麼樣。

**狀態查詢（status RPC）為什麼很弱：**worker 正在跑一次 tool call 的時候，它根本沒在聽訊息，所以這種呼叫不是卡住，就是回傳空的。
真正卡死的那個 worker，剛好就是不會回你的那個。

**三種真的可行的做法：**第一種要 worker 配合，最後一種完全不用。

1. 用訊息問。把一則狀態請求丟進 inbox（第 16 章），worker 下次 poll 時就會回答。這很準，前提是 worker 還在 poll。
2. 讀一個講好的進度檔。worker 每做一步就往雙方都知道的路徑加一行，讀的人完全不打斷它幹活。
3. 跟著讀存下來的 trajectory。runtime 本來就會把每一輪寫進磁碟（第 13 章），lead 直接讀那些輪次，worker 什麼都不用做。

**怎麼看出它卡住了：**後兩種做法順便就給了答案。看檔案最後一次寫入是什麼時候，沒有新的寫入就是沒有新的進展。
再配一個門檻，這就能拿來下判斷。慢的 tool call 跑起來同樣不會寫東西，所以門檻要設得比你預期最慢的呼叫還長。超過門檻，就當這個 worker 卡死了。
「卡在忙碌」這個失敗模式缺的就是這個觸發條件。有了門檻，lead 可以把 task 收回來，或是開一次 shutdown handshake（第 17 章），不用一直乾等。

**幫 worker 池加上預算：**poll 裡沒有任何東西會叫 worker 別再認領了。每個閒下來的 worker 都會再拿一個 task，所以收工的時機是預算用完，而不是活做完。

**要分配的到底是什麼：**有一個公開的 multi-agent 系統發現，光是 token 用量就解釋了大約 80% 的表現差異。
所以真正要分配的是 token，不是輪次。有四個旋鈕可以掛在看板和 worker 池上：

- 單一 task 的預算。每個 task 貼上看板時就寫好自己的步數上限與 token 上限，這樣一個失控的 task 吃不掉整場的資源。
- 併發上限。限制同時最多幾個 task 停在 `in_progress`。看板本來就在算這個數，超過上限的認領直接失敗就好。
- 模型配置。最強的模型放在最需要動腦的地方。計畫的好壞決定結果，所以強模型給 lead，例行的 worker 用便宜的就好。
- 搶佔（preemption）。超出預算的 worker，或是停擺超過門檻的 worker，手上的 task 會被收回看板。下一個認領的人從乾淨的狀態開始。

**把預算攤給 worker 看：**知道自己手上剩多少的 agent，花起來會跟只是拿到更大上限的 agent 不一樣。
這個結論出自書裡自己做的實驗，只有這一個來源。把它當成一個可以驗證的方向，別當成可以照抄的數字。

---

## 各系統做法

一個閒置 agent 如何找到並認領屬於自己的工作。

| | Claude Code |
| --- | --- |
| **Pros** | 沒有派工者瓶頸。閒置 agent 會持續拉工作，直到看板清空，外部建立的 task 也會被接手。 |
| **Cons** | 兩個閒置 agent 可能盯上同一個 task，得靠一個真正的 lock 加一次新鮮度檢查來裁定競爭。lead 指派不需要 lock，但無法擴展到超過 lead 的處理能力。 |
| **Why** | lead 逐一派 task 會成為瓶頸，worker 一做完就閒置又浪費剛載入的 context，所以讓 worker 自我組織。 |
| **How: idle behavior** | 短 poll loop，500ms 一個週期。先查 shutdown，再看未讀訊息（lead 先於 peer），接著嘗試認領，並宣告自己有空。 |
| **How: work claim** | 挑一個無人擁有、也沒有被阻擋的 task，在 lock 之下寫入擁有權，兩個 agent 不會搶到同一個。watcher 也會自動認領外部建立的 task。 |
| **How: self-organization** | Worker 從共享看板拉取工作（第 12 章）。lead 是 spawn worker 的整合者，不是 task 路由器。 |

---

## 哪裡會出錯

- **認領競爭（Claim race）：**兩個 agent 把一個 task 讀成無人擁有並雙雙認領，丟掉了其中一個 agent 的工作。在一個 file lock 內做認領，檢查與寫入一步做完，中間插不進別的 agent（第 12 章）。
- **被閒聊餓死（Starvation by chatter）：**peer 閒聊淹沒了一個 shutdown 請求，於是一個該停止的 agent 繼續 poll。在一般訊息之前先檢查 shutdown（第 16 章）。
- **過早認領被阻擋的工作：**一個 agent 認領了相依項尚未完成的 task，然後卡住。跳過任何 `blockedBy` 仍含未解 id 的 task（第 12 章）。
- **compaction 後身分遺失：**一個長時間運行的 teammate 在執行途中被自動 compaction（第 8 章），忘了自己的角色。保留 system prompt，讓角色得以存續。
- **卡在忙碌，或卡在閒置：**一個永遠抵達不了 `end_turn` 的階段永遠不會釋放；一個沒有出口的 poll 會空轉。依 stop 訊號結束（第 1 章）；每次 poll 都檢查 abort。
- **停擺沒人發現：**一個 worker 抓著 task 看起來很忙，其實毫無進展，看板就一直不會把它放回去。看它的進度檔最後一次寫入是什麼時候，超時就把 task 收回來。
- **整池預算失控：**閒下來的 worker 一直認領，於是要等預算花光才收得了工。每個 task 都給步數與 token 上限，同時能跑幾個也要設上限。
- **搶佔後重複寫入：**task 被放回看板又被別人認領時，舊的 worker 還在跑，於是兩個 agent 寫同一批檔案。等停止被確認之後再放回去（第 17 章）。

---

## 可執行程式

[`src/`](src/) 承接第 17 章並加上：

- [`autonomy.py`](src/autonomy.py)：在第 12 章看板之上的 outer loop 與 idle poll（由第 16 章的 `SpawnTeammate` 啟動每個 worker）。
- [`test.py`](src/test.py)：單一 worker 的機制、一個 `TeamCreate` 檢查、一次強制的認領競爭（16 條執行緒、一個 task、一個贏家）、一條多執行緒 pipeline，以及一個 spawn 工具檢查。
- [`demo.py`](src/demo.py)：lead 做一個步驟（`TeamCreate`、`TaskCreate`、`SpawnTeammate`）；接著 worker 從看板拉取 task，並在看板清空時自行停止。

機制段落裡的單一 worker `run_teammate` 是教學用的簡化版。

真正的團隊會同時跑一個 lead loop 與數個 worker loop，共用同一組看板與 inbox。

第 13 章在執行緒上啟動工作；第 12 章與第 16 章的 file lock 在競爭下保護共享狀態的安全。

並行 demo 與認領競爭測試把這一切串起來。

```bash
python sections/18-autonomy/src/test.py         # offline checks, no key
uv run python sections/18-autonomy/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code autonomy](https://github.com/yasasbanukaofficial/claude-code)：
  `utils/swarm/inProcessRunner.ts`（`runInProcessTeammate`、`waitForNextPromptOrShutdown`、`findAvailableTask`、`tryClaimNextTask`、`sendIdleNotification`）。
- [Claude Code claim and watch](https://github.com/yasasbanukaofficial/claude-code)：
  `utils/tasks.ts`（`proper-lockfile` 之下的 `claimTask`、`claimTaskWithBusyCheck`）、`hooks/useTaskListWatcher.ts`、`coordinator/coordinatorMode.ts`。
- [learn-claude-code · s17 autonomous agents](https://github.com/shareAI-lab/learn-claude-code)：章節定位。
- [ai-agent-book · 第 10 章](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter10.md)（《深入理解 AI Agent》，李博杰，以中文原版為準）：
  為什麼主動去拉的狀態查詢很弱、進度檔與跟讀 trajectory、用 mtime 判斷停擺、manager 模式的集中指派，
  以及團隊層級的資源調度（每個 subtask 的預算、併發上限、模型配置、搶佔）。
  其中「讓 agent 知道還剩多少預算」的結論出自書裡自己的實驗，只有這一個來源。
- [Plan-and-Act](https://arxiv.org/abs/2503.09572)（Erdogan 等，2025）：把 planner 和 executor 拆開，並指出計畫品質才是決定結果的那一項。
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)（Anthropic，2025）：
  光是 token 用量就解釋了大約 80% 的效能差異，其次才是 tool call 次數與模型選擇。
