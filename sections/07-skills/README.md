# 7 · Skills

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> A skill is a self-contained bundle of expertise, instructions plus any scripts and files, loaded only when a task needs it.

A skill turns a general agent into a specialist for one job.
It packages a workflow: the instructions to follow, plus any scripts to run and reference files to consult.
The agent loads a skill only when a task calls for it, so one agent can reach many specialized capabilities without loading them all up front.

Each skill is a folder with a `SKILL.md` file. The frontmatter names and describes the skill.
The body holds the instructions, and the folder can bundle extra scripts and reference files that load only when the skill uses them.

The agent needs to know that skills exist, but it should not pay for every skill body on every turn.

The skill system must:

1. List available skills cheaply.
2. Load full instructions only when a skill is selected.
3. Let skills point to extra files without loading them automatically.
4. Discover skills from built-in, user, project, plugin, or MCP sources.

Without this layer, the prompt is either too large or the agent cannot find its extensions.

---

## Mechanism

![Mechanism diagram](assets/07-skills.png)

Skills use progressive disclosure. The model sees only enough information to decide whether to load more.

1. **Metadata.** `name` and `description` from frontmatter, plus the skill's path. This cheap catalog rides in the system prompt every turn.
2. **Instructions.** The `SKILL.md` body. The model reads the file only when a task needs the skill.
3. **Resources.** Extra files in the skill folder. The model reads them with the same file tool when the instructions point to them.

No skill-specific tool is needed. Once the catalog names each skill and its path,
the agent loads a skill by reading its file with the normal Read tool. L2 and L3 are both just file reads.

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

- `load_skills` scans `SKILL.md` files and keeps only frontmatter for the catalog.
- `catalog_prompt` renders that catalog into the system prompt, one line per skill, with the path to read.
- The body and the resources are plain files. The normal Read tool loads them on demand, so there is no skill-specific tool.
- The Read tool is scoped to the skills directory, so a skill name can never escape into the filesystem.

### New: the store evolves

Loading is half of a skill system. The store also grows and decays (Hermes calls this skill evolution).

Growth is a write. The agent distills a finished workflow into a new skill, so the next run loads instructions instead of rediscovering them:

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

- `WriteSkill` is the model-facing tool around this function. Writing a skill is a side effect, so the section-3 gate asks unless a rule pre-approves it.
- The written file is a normal `SKILL.md`. Nothing special marks it: the next `load_skills` scan catalogs it like a hand-written skill.
- The name is resolved and checked the same way `read_tool` checks paths, so the store cannot be escaped from either direction.

Decay starts with measurement. Loading a skill is the use signal, so `read_tool` records it as a side effect of the read:

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

- The record keys on the skill's folder name, taken from the path the model read. A resource read (L3) does not bump it, only the `SKILL.md` body (L2).
- A skill with no record has `last_used_at` 0, so never-used skills count as stale too.
- `stale_skills` is a report, not an action. Deciding what to do with it is a curator's job; Hermes runs a background curator agent on the same signal (archive, consolidate, pin).
- The data flow is a loop across runs: read bumps `.usage.json`, the curator reads it, the catalog reflects what survives, and `WriteSkill` feeds new entries in.

### How it integrates

The loop does not change. Reading a skill returns a tool result that enters `messages[]`.

The catalog belongs in the system prompt. The body enters the conversation only after the model reads the file. Resource files are read later only if needed.

Because loaded skill text lives in `messages[]`, it can be compacted like any other message when the context fills (section 8). Keep skill bodies short and point to files for large references.

---

## Per system

How each agent describes, triggers, and finds skills.

| | Claude Code | Hermes Agent |
| --- | --- | --- |
| **Pros** | The catalog fits a budget. A skill can fork into a subagent and scope its tools. | A curator merges new skills and archives stale ones. Hub installs are checked. |
| **Cons** | Vague descriptions hide skills. Forked skills lose live context. | Vague descriptions hide skills too. Automatic changes need pins and staged approvals. |
| **Why** | Skills also fork and scope tools, so a plain file read is not enough. | Loading is half the job. The store itself must grow and decay. |
| **How: skill format** | `SKILL.md` folder with frontmatter and body. Frontmatter can limit tools or pick a model. | Same shape, sorted into category folders. |
| **How: load trigger** | A `Skill` tool call injects the body. Matching files can also fire it. | `skill_view` returns the body plus linked files and bumps use counts. |
| **How: discovery** | Built-in, user, project, plugin, and MCP sources. Legacy slash commands use the same machinery. | Bundled, optional, user, plugin, and GitHub hub sources. |

---

## Failure modes

- **Skill never fires.** The description is too vague. Write trigger-shaped descriptions.
- **Catalog gets too large.** Too many skills can crowd the prompt. Keep skills focused and let the loader trim.
- **Body is lost after compaction.** Re-read the skill file or keep the body short.
- **Path traversal.** The catalog hands the model a path. Scope the Read tool to the skills directory so `../` cannot escape it.
- **Forked skill loses live context.** Use forked skills only for self-contained work.

---

## Runnable

[`src/`](src/) carries 06 forward and adds:

- [`skills.py`](src/skills.py): catalog scan, the system-prompt listing, a path-scoped `Read` tool, and the evolution half (`WriteSkill`, `record_use`, `stale_skills`).
- `skills/<name>/SKILL.md`: sample skills, including one with a resource file.
- [`loop.py`](src/loop.py): unchanged because loading a skill is just a file read.
- [`test.py`](src/test.py): checks catalog scan, the prompt listing, file loads, path-traversal rejection, usage bumps, staleness, and an agent-written skill entering the catalog.
- [`demo.py`](src/demo.py): the agent uses a skill, then saves a new one; the closing scan shows the store grew.

```bash
python sections/07-skills/src/test.py         # offline checks, no key
uv run python sections/07-skills/src/demo.py  # live demo, needs a key
```

---

## Sources

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code):
  `skills/loadSkillsDir.ts`, `skills/bundledSkills.ts`, `skills/mcpSkillBuilders.ts`, `tools/SkillTool/SkillTool.ts`, `tools/SkillTool/prompt.ts`.
- [Hermes Agent source](https://github.com/NousResearch/hermes-agent):
  `tools/skills_tool.py` (`skills_list`, `skill_view`), `tools/skill_usage.py`, `hermes_cli/curator.py`, `tools/skills_hub.py`, `tools/skills_ast_audit.py`.
- [Anthropic Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices): progressive disclosure levels.
- [learn-claude-code · s07_skill_loading](https://github.com/shareAI-lab/learn-claude-code): section framing.
