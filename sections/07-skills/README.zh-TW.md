# 7 · Skills

[English](README.md) · **繁體中文**

> skill 是一個自成一體的專長包，包含指令，還有需要用到的 script 和檔案，只在某個任務需要時才載入。

skill 讓一個通用的 agent，變成專做某件事的專家。
它打包的是一整套工作流程：要遵循的指令，加上需要執行的 script 和要參考的檔案。
agent 只在任務用得到時才載入某個 skill，所以一個 agent 可以擁有很多專門能力，卻不用一開始就把它們全部扛在身上。

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

skill 使用 progressive disclosure。模型只會看到剛好足夠的資訊，來決定要不要載入更多。

1. **Metadata。** 來自 frontmatter 的 `name` 和 `description`，再加上這個 skill 的路徑。這份低成本的 catalog 每個 turn 都待在 system prompt 裡。
2. **Instructions。** `SKILL.md` 的本文。只有在某個任務需要這個 skill 時，模型才會去讀這個檔案。
3. **Resources。** skill 資料夾裡的額外檔案。指令指向它們時，模型用同一個 file tool 讀取。

不需要專門的 skill tool。只要 catalog 列出每個 skill 的名稱和路徑，agent 就用一般的 Read tool 去讀那個檔案來載入 skill。L2 和 L3 都只是讀檔而已。

```mermaid
flowchart LR
    D["scan dirs · name + description + path"] --> C["catalog in system prompt"]
    C --> M{{model call}}
    M -->|Read SKILL.md| L["skill body enters messages[]"]
    L --> M
    M -->|body cites a file| R["Read resource file"]
    R --> M
```

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

### How it integrates

迴圈不會改變。讀取一個 skill，會回傳一個進入 `messages[]` 的 tool 結果。

catalog 屬於 system prompt。本文只有在模型讀了那個檔案之後，才會進入這段對話。resource 檔案只有在需要時才會稍後讀取。

因為載入的 skill 文字存在於 `messages[]`，它可以像其他訊息一樣被壓縮。讓 skill 本文保持簡短，大型參考資料則指向檔案。

---

## 各系統做法

各 agent 如何描述、觸發並找到 skill。

| System | Skill format | Load trigger | Discovery |
| --- | --- | --- | --- |
| **Claude Code** | 帶有 frontmatter 和本文的 `SKILL.md` 資料夾。 | invoke `Skill` tool。 | built-in、user、project、plugin 和 MCP 來源。 |

### Claude Code

- `loadSkillsDir.ts` 在一定預算內建立可見的 catalog。
- `SkillTool.ts` 以 `newMessages` 回傳本文。
- 可見的結果是一則簡短的啟動訊息。
- frontmatter 可以包含 `when_to_use`、`allowed-tools`、`context`、`paths`、`model` 和 `user-invocable`。
- `context: 'fork'` 會在一個 forked subagent 中執行該 skill。
- `paths` 可以在符合條件的檔案被動到時啟用 skill。
- MCP 提供的 skill 和舊的 `.claude/commands/` 使用同一套機制。
- 只提供指令的 skill 不需要專門的 tool。Claude Code 之所以用 `SkillTool.ts` 包住本文載入，是因為它的 skill 還會 fork 並限制可用工具，這是單純讀檔做不到的。

> **取捨：** 低成本的 catalog 讓情境保持精簡。它也仰賴好的描述。如果描述含糊不清，模型可能永遠不會載入這個 skill。

---

## 失效模式

- **skill 從不觸發。** 描述太含糊。寫成帶有觸發條件形狀的描述。
- **catalog 變得太大。** skill 太多會擠爆 prompt。讓 skill 保持聚焦，並讓 loader 做裁剪。
- **壓縮後本文遺失。** 重新讀取該 skill 檔案，或讓本文保持簡短。
- **Path traversal。** catalog 會把路徑交給模型。把 Read tool 的範圍限制在 skills 目錄，讓 `../` 無法逃出去。
- **forked skill 失去即時情境。** 只在自成一體的工作上使用 forked skill。

---

## 可執行程式

[`src/`](src/) 沿用 06 並加上：

- [`skills.py`](src/skills.py)：catalog 掃描、system prompt 列表，以及一個限定範圍的 `Read` tool。
- `skills/<name>/SKILL.md`：範例 skill，包含一個帶有 resource 檔案的 skill。
- [`loop.py`](src/loop.py)：未變動，因為載入一個 skill 只是讀一個檔案。
- [`test.py`](src/test.py)：檢查 catalog 掃描、prompt 列表、檔案載入，以及 path traversal 的拒絕。

```bash
python sections/07-skills/src/test.py         # offline checks, no key
uv run python sections/07-skills/src/demo.py  # live demo, needs a key
```

---

## 出處

- Claude Code 原始碼：`skills/loadSkillsDir.ts`、`skills/bundledSkills.ts`、`skills/mcpSkillBuilders.ts`、`tools/SkillTool/SkillTool.ts`、`tools/SkillTool/prompt.ts`。
- [Anthropic Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)：progressive disclosure 的層級。
- learn-claude-code · s07_skill_loading：章節框架。
