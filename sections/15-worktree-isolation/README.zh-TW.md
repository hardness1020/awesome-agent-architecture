# 15 · Worktree isolation

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 給平行運作的 agent 各自獨立的工作目錄。

單一工作目錄是共用的可變狀態。如果兩個 agent 同時寫入同一個檔案，其中一個可能覆蓋掉另一個的成果。

task 系統決定有哪些工作要做。subagent 決定工作怎麼拆分。worktree isolation 則把寫入隔開：每個 agent 寫在自己的目錄，不會互相干擾。

每個工作單元都有自己的 checkout 和 branch。agent 的檔案工具與 shell 工具會在那個 checkout 裡解析路徑。

隔離層必須：

1. 為每個工作單元建立一份私有 checkout。
2. 把工具綁定到那份 checkout。
3. 拒絕會逃出 worktree 根目錄的名稱。
4. 移除乾淨的 worktree，保留有變更的以供審查。

沒有這一層，好幾個 agent 同時改同一個目錄，檔案就可能被改壞。

---

## 機制

![機制圖](assets/15-worktree-isolation.png)

有兩個部分：

1. 每個工作單元有自己私有的 git worktree。
2. 每個 context 有自己綁定的工作目錄。

這個綁定必須限定在 agent context 的範圍內。全域的 `chdir` 會影響同一個 process 裡的其他 agent。

- 每個 worktree 都是同一個 repo 在自己 branch 上的 checkout。
- slug 會變成路徑，所以在任何路徑組合之前先驗證它。
- 工具從 context 讀取 `get_cwd()`，而不是從全域 process cwd 讀取。
- 收尾清理時，只移除乾淨的 worktree。有變更的會保留下來供審查。

### New: worktree 與 cwd 綁定

`worktree.py` 驗證一個 slug、建立一個 worktree，並透過 context variable 綁定 cwd：

```python
_cwd = contextvars.ContextVar("cwd", default=None)   # per-context cwd

@contextlib.contextmanager
def cwd_override(path):
    token = _cwd.set(str(path))                       # bind, never os.chdir
    try:
        yield
    finally:
        _cwd.reset(token)

def remove(repo_root, slug, force=False):
    path = _path(repo_root, slug)                     # _path validates the slug first
    if not force and changes(path):
        return False                                  # keep for review
    _git(repo_root, "worktree", "remove", "--force", str(path))
    _git(repo_root, "branch", "-D", f"worktree-{slug}")
    return True
```

- `cwd_override` 只影響當前的 context。
- 工具把 `get_cwd()` 傳給子行程與檔案操作。
- `create` 執行 `git worktree add -B worktree-<slug>`。
- `validate_slug` 拒絕路徑穿越與不允許的字元。
- `remove` 除非強制，否則拒絕移除有變更的 worktree。

### 如何整合

隔離從 loop 外面包住一個 turn：

```python
wt = worktree.create(repo, "agent-1")                 # src/demo.py
with worktree.cwd_override(wt):
    run_turn([{"role": "user", "content": prompt}], model, reg, session)
worktree.remove(repo, "agent-1")                       # clean -> remove, dirty -> keep
```

loop 與 subagent 路徑不需要特殊邏輯。只有工具看到的工作目錄改變了。

若要讓模型能自行選擇這個模式，在 `Agent` 工具的 schema 加上 `isolation` 選項，並在 `spawn` 裡分支處理。

---

## 各系統做法

各系統如何隔離平行工作並在事後清理。

| | Claude Code |
| --- | --- |
| **Pros** | 真正的檔案系統隔離，diff 也乾淨。有變更的 worktree 會留下來供審查，成果不會默默遺失。 |
| **Cons** | 要付出硬碟空間、建置時間，以及之後的 merge 步驟。 |
| **Why** | 好幾個 agent 同時寫同一個目錄不安全，所以每個工作單元都在自己的 checkout 裡寫。 |
| **How: isolation unit** | 每個 task 或 session 一個 git worktree，各自有自己的 branch。模型開 subagent 時可以自己要求一個。 |
| **How: binding** | subagent 用限定範圍的 cwd，並行的 agent 互不影響。session 模式改 process cwd。綁定存在於 cwd 範圍裡，task 記錄不存。 |
| **How: cleanup** | 移除乾淨的 worktree。有變更的會保留，除非使用者明確捨棄變更。週期性的清掃會移除舊的臨時 worktree。 |

---

## 哪裡會出錯

- **slug 裡的路徑穿越：**在路徑組合或 git 指令之前先驗證。
- **移除時默默遺失：**除非使用者明確捨棄變更，否則保留有變更的 worktree。
- **cwd 在 agent 之間外洩：**對並行的 subagent 使用 context-local 的 cwd。
- **陳舊 worktree 堆積：**只清掃已知的臨時 worktree。
- **fork 後讀到陳舊內容：**告訴 fork 出來的子行程重新讀取 worktree 裡的檔案。

---

## 可執行程式

[`src/`](src/) 承接第 14 章並加上：

- [`worktree.py`](src/worktree.py)：slug 驗證、worktree 建立、context-local 的 cwd，以及安全移除。
- [`test.py`](src/test.py)：檢查兩個 agent 在各自的 worktree 裡寫入，以及乾淨/有變更的移除閘門。
- [`demo.py`](src/demo.py)：在 worktree 裡跑一個 live turn。

loop 與 subagent 路徑不變。隔離透過綁定 cwd 來包住 turn。

```bash
python sections/15-worktree-isolation/src/test.py         # offline checks, real git, no key
uv run python sections/15-worktree-isolation/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code 原始碼](https://github.com/yasasbanukaofficial/claude-code)：`tools/EnterWorktreeTool/`、`tools/ExitWorktreeTool/`、`utils/worktree.ts`、`utils/cwd.ts`、`tools/AgentTool/AgentTool.tsx`。
- [learn-claude-code · s18_worktree_isolation](https://github.com/shareAI-lab/learn-claude-code)：章節框架。
