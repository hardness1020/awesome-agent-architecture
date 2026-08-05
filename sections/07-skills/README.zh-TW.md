# 7 · Skills

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> skill 是一個自成一體的專長包，包含指令，還有需要用到的 script 和檔案，只在某個任務需要時才載入。

skill 讓一個通用的 agent，變成專做某件事的專家。
它打包的是一整套工作流程：要遵循的指令，加上需要執行的 script 和要參考的檔案。
agent 只在任務用得到時才載入某個 skill，所以一個 agent 可以擁有很多專門能力，卻不用一開始就全部載入。

每個 skill 是一個資料夾，裡面有一個 `SKILL.md` 檔案。frontmatter 為這個 skill 命名並描述它。
本文放的是指令，而資料夾還可以打包額外的 script 和參考檔案，只有在 skill 用到時才載入。

agent 需要知道有哪些 skill 存在，但它不應該為了每個 skill 的本文，在每一個 turn 都付出代價。

skill 系統必須做到：

1. 用很低的成本列出可用的 skill。
2. 只在某個 skill 被選中時，才載入完整指令。
3. 讓 skill 可以指向額外的檔案，而不會自動載入它們。
4. 從 built-in、user、project、plugin 或 MCP 來源探索 skill。

沒有這一層，prompt 不是太大，就是 agent 找不到它的擴充功能。

---

## 機制

![機制圖](assets/07-skills.png)

skill 使用 progressive disclosure。模型只會看到剛好足夠的資訊，來決定要不要載入更多。

1. **Metadata。** 來自 frontmatter 的 `name` 和 `description`，再加上這個 skill 的路徑。這份 catalog 只佔少量 token，所以一直放在 system prompt 裡。
2. **Instructions。** `SKILL.md` 的本文。只有在某個任務需要這個 skill 時，模型才會去讀這個檔案。
3. **Resources。** skill 資料夾裡的額外檔案。指令指向它們時，模型用同一個 file tool 讀取。

不需要專門的 skill tool。只要 catalog 列出每個 skill 的名稱和路徑，agent 就用一般的 Read tool 去讀那個檔案來載入 skill。L2 和 L3 都只是讀檔而已。

有三件事會決定 progressive disclosure 到底管不管用。

- **description 是路由條件，不是摘要。** 模型在決定要不要載入之前，只看得到 catalog 那一行。
  所以要寫清楚什麼時候該用、什麼時候不該用，最好附一個反例。只寫主題名稱的描述，等於叫模型自己猜。
- **catalog 放哪裡是可以選的。** 這份列表可以放在 system prompt，也可以塞進某個啟用用 tool 的 description 裡。
  open standard 兩種都允許。放 system prompt，每個 session 的 prefix 都要付這筆 token；放進 tool，prefix 比較小，列表變成 tool schema 的一部分。
- **progressive disclosure 是便宜，不是免費。** catalog 至少要被 prefill 一次，載入的本文在被壓縮之前也一直佔著 context。
  第一個 turn 之後 prefix 就被快取住，後面的成本很低。所以真正要抓的預算是 catalog 掛了幾個 skill，而不是本文被讀了幾次。

同一套做法現在也長到 tool 這一層了。與其把每個 tool schema 都塞進 prefix，harness 只留名稱和一行描述，完整 schema 等模型要用的時候再拉。
OpenAI 的 Responses API 用 `defer_loading` 標記 tool，Claude Code 把 tool search 用在 MCP server 上，Codex CLI 則用 BM25 對自己的 tool 列表排序。
拉進來的 schema 會接在 context 尾端，所以快取住的 prefix 不會被打掉。
skill 是這個 repo 第一次碰到 progressive disclosure 的地方，現在 tool 定義本身也內建了這件事（第 2 章）。

### New: scan the skills and list them in the prompt

```python
@dataclass
class Skill:                                   # src/skills.py
    name: str
    description: str                           # L1: frontmatter -> the catalog
    path: Path                                # SKILL.md; the body is read on demand

def load_skills(skills_dir) -> list[Skill]:    # L1: scan <dir>/<name>/SKILL.md at startup
    skills = []
    for sub in sorted(Path(skills_dir).iterdir()):
        meta, _ = _split((sub / "SKILL.md").read_text())   # keep frontmatter, not the body
        skills.append(Skill(meta["name"], meta["description"], sub / "SKILL.md"))
    return skills

def catalog_prompt(skills, base_dir) -> str:   # L1: the block added to the system prompt
    lines = [f"- {s.name}: {s.description} (read {s.path.relative_to(base_dir)})" for s in skills]
    return "Available skills (read a skill's path with the Read tool):\n" + "\n".join(lines)
```

- `load_skills` 掃描 `SKILL.md` 檔案，只保留 frontmatter 給 catalog。
- `catalog_prompt` 把這份 catalog 渲染進 system prompt，每個 skill 一行，附上要讀取的路徑。
- 本文和 resource 都是普通檔案。一般的 Read tool 在需要時載入它們，所以不需要專門的 skill tool。
- Read tool 的範圍限制在 skills 目錄內，所以 skill 名稱永遠無法逃逸到檔案系統其他地方。

### New: the store evolves

skill 系統不是只有載入這件事。skill store 本身也會成長、也會汰舊（Hermes 稱之為 skill 演化）。

成長靠寫入。agent 把一段做完的工作流程沉澱成新的 skill，下一次執行就直接載入指令，不用重新摸索：

```python
def write_skill(skills_dir, name, description, body) -> Path:   # src/skills.py
    base = Path(skills_dir).resolve()
    target = (base / name / "SKILL.md").resolve()
    if not target.is_relative_to(base):              # a name can never escape the skills dir
        raise ValueError(f"skill name {name!r} escapes the skills dir")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n")
    return target
```

- `WriteSkill` 是包住這個函式、面向模型的 tool。寫入 skill 會改動檔案系統，屬於有副作用的操作，所以第 3 章的權限閘門預設會先徵詢使用者；只有 allow 規則預先核准過，才會直接放行。
- 寫出來的檔案就是普通的 `SKILL.md`。沒有任何特殊標記：下一次 `load_skills` 掃描會把它當成一般的 skill 編入 catalog。
- 名稱的解析和檢查方式跟 `read_tool` 檢查路徑一樣，所以不論讀或寫，都逃不出 skills 目錄。

要汰舊，得先量測。載入 skill 本身就是使用訊號，所以 `read_tool` 在讀檔的同時順手記錄：

```python
if target.name == "SKILL.md":                # inside read_tool's read()
    record_use(base, target.parent.name)     # loading a skill counts as use
```

```python
def record_use(skills_dir, name, now=None) -> dict:
    path = Path(skills_dir) / USAGE_FILE     # .usage.json, one record per skill
    usage = json.loads(path.read_text()) if path.exists() else {}
    entry = usage.setdefault(name, {"uses": 0})
    entry["uses"] += 1
    entry["last_used_at"] = now if now is not None else time.time()
    path.write_text(json.dumps(usage))
    return entry

def stale_skills(skills_dir, skills, now=None, stale_after=STALE_AFTER) -> list[str]:
    usage = ...                                  # load .usage.json, default {}
    return [s.name for s in skills
            if now - usage.get(s.name, {}).get("last_used_at", 0) >= stale_after]
```

- 這筆記錄以 skill 的資料夾名稱為 key，取自模型讀取的路徑。讀 resource（L3）不會累計，只有讀 `SKILL.md` 本文（L2）才算。
- 沒有記錄的 skill，`last_used_at` 是 0，所以從未用過的 skill 也算 stale。
- `stale_skills` 是一份報告，不是一個動作。要怎麼處理是 curator 的工作；Hermes 用一個背景 curator agent 處理同樣的訊號（封存、整併、釘選）。
- 資料流是一個跨執行的 loop：讀取更新 `.usage.json`，curator 讀它，catalog 反映留下來的 skill，`WriteSkill` 再補進新條目。

**什麼時候該寫。** demo 的做法是一次成功就寫：跑完一段流程，呼叫一次 `WriteSkill`，下一次掃描就把它編進 catalog。
這是能把整個 loop 演出來的最小規則，也是可執行程式碼實際在做的事。

書裡的門檻更高。要成為正式能力，證據得重複出現，至少兩次沒有失敗的執行呈現同一個模式，而且驗證那一步不能來自提出它的那次執行。
Voyager 也是同一套規則：環境確認這個 skill 真的有用，它才進得了 library。
寫之前先搜一下 store，找得到相近的就去改它，不要再開一個重複的。本文裡也要留下這次踩到的坑，而不是只留走得通的那條路。
兩種立場都成立。一次成功比較好教機制，demo 也短。門檻則是在 store 長到幾百個的時候，擋住那些只用過一次的筆記。

中間插一個 candidate 步驟，可以兩邊兼顧。沉澱出來的流程先落成 candidate，不直接進 catalog，經過起草、測試、評估、修訂才升級。
Anthropic 的 Skill Creator 就是跑這個 loop。放到這一章的程式碼裡，就是多一個暫存資料夾，`load_skills` 先跳過它，等 curator 升級才收。

**整併是離線做的。** curator 是排程跑的，不是即時跑的。書裡叫它 sleep-time learning，分成五步：

1. **觸發。** 排程時間到、系統閒置，或 store 大小超過門檻。
2. **定位。** 先對 store 做一次快照，後面每一步才都能回滾。
3. **蒐集與合併。** 讀使用記錄和最近幾次執行，把幾乎重複的 skill 併成一個，順便把 candidate 收進來。
4. **驗證與核准。** 拿產生它們的那幾次執行去檢查合併後的本文。沒過的就不收。
5. **修剪與建索引。** 依固定規則封存過期 skill，然後重建 catalog。

放在離線做，本身就是一條安全邊界。線上 loop 只負責執行和記錄，跑到一半絕不去動 store。
一次剛好成功的執行沒辦法把自己升級，agent 從外面讀進來的文字，也沒辦法在兩個 turn 之間變成永久指令。

### How it integrates

loop 不用改。讀取 skill 就是一次普通的工具呼叫，tool 結果照樣進入 `messages[]`。

三層各有位置：catalog 放在 system prompt。skill 本文要等模型讀了 `SKILL.md`，才會進到對話裡。resource 檔案則等到真的用到時才讀。

載入後的 skill 文字就在 `messages[]` 裡，所以之後 context 不夠用時，它會跟其他訊息一起被壓縮（第 8 章）。skill 本文要寫短，大型參考資料改成指向檔案。

---

## 各系統做法

各 agent 如何描述、觸發並找到 skill。

| | Claude Code | Hermes Agent |
| --- | --- | --- |
| **Pros** | catalog 建立時有預算上限。skill 可以 fork 成 subagent，還能限制可用的 tool。 | curator 會整併新 skill、封存過期的。hub 安裝會經過檢查。 |
| **Cons** | 描述太含糊，模型就不會去載入。forked skill 拿不到即時情境。 | 描述含糊在這裡一樣會埋沒 skill。自動改動需要釘選和暫存核准來把關。 |
| **Why** | skill 還要 fork、還要限制 tool，單純讀檔不夠用。 | 載入只是一半，store 本身還要能成長、能汰舊。 |
| **How: skill format** | 帶有 frontmatter 和本文的 `SKILL.md` 資料夾。frontmatter 還能限制 tool、指定模型。 | 同樣的形式，依分類資料夾整理。 |
| **How: load trigger** | invoke `Skill` tool，本文注入對話。動到符合條件的檔案也會觸發。 | `skill_view` 回傳本文、列出關聯檔案，並累計使用次數。 |
| **How: discovery** | built-in、user、project、plugin 和 MCP 來源。舊的 slash command 走同一套機制。 | bundled、optional、user、plugin 和 GitHub hub 來源。 |

---

## 哪裡會出錯

- **skill 從不觸發：**描述太含糊。把觸發條件直接寫進描述裡。
- **catalog 變得太大：**skill 太多會擠爆 prompt。讓 skill 保持聚焦，並讓 loader 做裁剪。
- **壓縮後本文遺失：**重新讀取該 skill 檔案，或讓本文保持簡短。
- **Path traversal：**catalog 會把路徑交給模型。把 Read tool 的範圍限制在 skills 目錄，讓 `../` 無法逃出去。
- **forked skill 失去即時情境：**只在自成一體的工作上使用 forked skill。
- **供應鏈裡的毒 skill：**裝進來的第三方 skill 本質是外部內容，卻是當成指令載入的，殺傷力比一個被下毒的網頁還大，因為 catalog 已經替它背書了。
  安裝前把本文和附帶的 script 都讀過，版本要釘住，更新時再看一次。
- **注入的文字變成永久的：**`messages[]` 裡的 prompt injection，session 結束就沒了；同一段文字沉澱進 `SKILL.md`，之後每次執行都會載入。
  沒審過的外部內容絕不能餵給 `WriteSkill`。新 skill 先當 candidate 放著，等另一道流程核准；也絕不讓 skill 去改那道核准閘門。
- **使用次數會高估學習成效：**載入不等於照做。次數只說明 catalog 路由對了，不代表這個 skill 改變了結果。
  skill 有沒有被觸發、那次執行有沒有變好，要當成兩個數字分開看。

---

## 可執行程式

[`src/`](src/) 沿用 06 並加上：

- [`skills.py`](src/skills.py)：catalog 掃描、system prompt 列表、限定範圍的 `Read` tool，以及演化那一半（`WriteSkill`、`record_use`、`stale_skills`）。
- `skills/<name>/SKILL.md`：範例 skill，包含一個帶有 resource 檔案的 skill。
- [`loop.py`](src/loop.py)：未變動，因為載入一個 skill 只是讀一個檔案。
- [`test.py`](src/test.py)：檢查 catalog 掃描、prompt 列表、檔案載入、path traversal 的拒絕、使用計數、staleness，以及 agent 寫出的 skill 進入 catalog。
- [`demo.py`](src/demo.py)：agent 用了一個 skill，接著存下一個新的；收尾的掃描顯示 store 長大了。

```bash
python sections/07-skills/src/test.py         # offline checks, no key
uv run python sections/07-skills/src/demo.py  # live demo, needs a key
```

---

## 出處

- [Claude Code 原始碼](https://github.com/yasasbanukaofficial/claude-code)：
  `skills/loadSkillsDir.ts`、`skills/bundledSkills.ts`、`skills/mcpSkillBuilders.ts`、`tools/SkillTool/SkillTool.ts`、`tools/SkillTool/prompt.ts`。
- [Hermes Agent 原始碼](https://github.com/NousResearch/hermes-agent)：
  `tools/skills_tool.py`（`skills_list`、`skill_view`）、`tools/skill_usage.py`、`hermes_cli/curator.py`、`tools/skills_hub.py`、`tools/skills_ast_audit.py`。
- [Anthropic Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)：progressive disclosure 的層級。
- [learn-claude-code · s07_skill_loading](https://github.com/shareAI-lab/learn-claude-code)：章節框架。
- [ai-agent-book](https://github.com/bojieli/ai-agent-book)：`book/chapter2.md`、`book/chapter8.md`，以中文原版為準。
- [Agent Skills open standard](https://agentskills.io)：catalog 放哪裡，system prompt 或啟用用 tool 的 description。
- Deferred tool loading：OpenAI Responses API tool search（`defer_loading`）、Claude Code MCP tool search、Codex CLI `search_tool`。
- [Claude Code · prompt caching](https://code.claude.com/docs/en/prompt-caching)：載入的 skill 本文會落在哪裡、成本是多少。
- [Voyager](https://arxiv.org/abs/2305.16291)：環境驗證過，skill 才進得了 library。
- [Anthropic Skill Creator](https://github.com/anthropics/skills)：升級之前先起草、測試、評估、修訂。
- Lin et al.，[arXiv:2605.30621](https://arxiv.org/abs/2605.30621)，轉引自書：更新有沒有落地、有沒有幫上忙，是兩個要分開量的數字。
