# 7 · Skills

> A skill is a manifest plus instructions, loaded into context only when invoked.

Skills are capabilities you add on demand, each a folder with a `SKILL.md`: frontmatter metadata plus a body of instructions. Say you want the agent to follow your React conventions, your SQL style guide, and your PDF workflow. The naive fix is to paste all of it into the system prompt (section 10); now every model call, even one that edits a CSS color, carries thousands of tokens of irrelevant instructions, paid on every turn as the signal-to-noise drops. So something must:

1. Tell the agent what capabilities exist, cheaply, on every turn.
2. Load the full instructions only when a capability is actually needed.
3. Discover those capabilities from multiple places (built in, user, project, plugins).

Leave this out and you choose between a bloated always-on prompt or an agent that does not know its own extensions exist.

---

## Mechanism

**Progressive disclosure.** A skill reveals itself to the model in three levels, each loaded only when needed (Anthropic's Agent Skills best practices):

1. **Metadata.** `name` + `description` from the `SKILL.md` frontmatter. Always in context as the cheap catalog; the model reads it to judge relevance.
2. **Instructions.** The `SKILL.md` body. Read into the conversation only when the model invokes the skill.
3. **Resources.** Files bundled in the skill folder. Never auto-loaded; the body points to them and the model reads each only when the task needs it.

The model pays for level N only after level N-1 sent it there, so context stays lean.

```mermaid
flowchart LR
    D["scan dirs · L1 name + description"] --> C["catalog: always in context"]
    C --> M{{model call}}
    M -->|invoke Skill| L["L2: load SKILL.md body"]
    L --> M
    M -->|body cites a file| R["L3: agent's Read tool pulls it"]
    R --> M
    M -->|done| X(["only what was needed is loaded"])
```

### New: scan (L1) and the Skill tool (L2)

```python
@dataclass
class Skill:                                   # src/skills.py
    name: str
    description: str                           # L1: frontmatter -> the catalog
    path: Path                                # SKILL.md; the body is read on invoke

def load_skills(skills_dir) -> list[Skill]:    # L1: scan <dir>/<name>/SKILL.md at startup
    skills = []
    for sub in sorted(Path(skills_dir).iterdir()):
        meta, _ = _split((sub / "SKILL.md").read_text())   # keep frontmatter, not the body
        skills.append(Skill(meta["name"], meta["description"], sub / "SKILL.md"))
    return skills

def skill_tool(skills) -> Tool:                # L2: read the body from disk on invoke
    by_name = {s.name: s for s in skills}
    def load(a):
        _, body = _split(by_name[a["name"]].path.read_text())
        return body                            # tool result -> enters messages[]
    return Tool("Skill", load, is_read_only=True)
```

- `load_skills` ([`src/skills.py`](src/skills.py)) scans `<name>/SKILL.md` and keeps only each frontmatter: L1, the cheap catalog. Claude Code scans `.claude/skills`; the demo scans a local `skills/` dir.
- `skill_tool` reads the matching body from disk on invoke: L2, the instructions, paid for only when the model picks the skill. It is the only skill-specific tool.
- **L3 is plain file access, not a skill tool.** The body points to bundled files (a big field map, a script) by path; the agent reads them with its normal `Read` tool, or runs them with `Bash`, only when the task needs them. The demo bundles `pdf-fill/reference.md` to show the structure; this minimal section ships no file tool (that arrives with the section-3 sandbox), so the body cites the file and the read happens there.

### How it integrates

No loop change. A skill loads through the section-2 tool runtime like any other tool, so [`src/loop.py`](src/loop.py) is unchanged from section 5:

- The `Skill` body returns as ordinary tool-result content, so it lands in `messages[]`, not the system prompt (section 10). That is progressive disclosure in one loop: the catalog rides in the prompt, the body enters the conversation on invoke, and a referenced resource later via the file tool, each only as the model asks.
- Because each is just a message, it is subject to compaction (section 8) like any other, and a vague `description` means the model never invokes the skill at all.
- Skills load by registered name, never an arbitrary path. A bundled resource is read by the file tool, which scopes the path to the skill dir (`resolveSkillFilePath`) so a crafted reference cannot escape it.

---

## Per system

How each agent describes, triggers, and finds its skills.

| System | Skill format | Load trigger | Discovery |
| --- | --- | --- | --- |
| **Claude Code** | `SKILL.md` folder: YAML frontmatter (`name`, `description`, `when_to_use`, `allowed-tools`, `context`, `paths`) + body | `Skill` tool invoke; catalog visible every turn via budgeted listing | `loadSkillsDir.ts` scans managed/user/project/`--add-dir`; `bundledSkills.ts` built-ins; plus plugin and MCP skills |
| *(more soon)* | | | |

### Claude Code

- **Catalog assembly.** `loadSkillsDir.ts` builds the listing within budget (`formatCommandsWithinBudget`, `getCharBudget`).
- **Invoke is indirect.** `tools/SkillTool/SkillTool.ts` returns the body as `newMessages` injected into the conversation; the visible tool result is just `Launching skill: {name}`.
- **Frontmatter drives behavior.** `parseSkillFrontmatterFields` reads `context: 'fork'` (run as a forked sub-agent, section 6), a `model` override, `paths` (conditional skills activated only when matching files are touched), and `user-invocable` (whether `/name` works).
- **One machinery, many sources.** It folds in legacy `.claude/commands/` and MCP-served skills via `mcpSkillBuilders.ts`.

> **Trade-off:** the two-level split buys a near-free catalog and full bodies only when needed, but it leans entirely on the `description` and `when_to_use` text being good enough for the model to self-select. A bad description means the skill is never invoked even though it exists; an always-on prompt would have guaranteed the instructions were seen.

---

## Failure modes

- **Skill never fires.** A vague `description` or missing `when_to_use` reads as irrelevant, so the model never invokes the skill. Mitigation: write trigger-shaped descriptions within the per-entry budget so they are not truncated.
- **Catalog crowds out context.** Hundreds of skills push the listing past budget, trimming descriptions to names and eroding selection. Mitigation: the `SKILL_BUDGET_CONTEXT_PERCENT` cap and per-entry truncation bound it; the real fix is fewer, sharper skills.
- **Body evaporates after compaction.** The loaded `SKILL.md` rides in `messages[]`, so a long run can compact or drop it (section 8) and the agent forgets mid-task. Mitigation: re-invoke, or keep the body short and let it point at files read on demand.
- **Path traversal on load.** Loading by raw file path lets a crafted name escape the skill directory. Mitigation: invoke by registered name; `resolveSkillFilePath` resolves bundled paths against the skill dir and rejects escapes.
- **Forked skill loses the main thread.** A `context: 'fork'` skill runs in an isolated sub-agent (section 6); only its final result returns. Mitigation: use `fork` only for self-contained work, keep `inline` (the default) when the skill must edit live conversation state.

---

## Runnable

[`src/`](src/) carries 06 forward and adds:

- [`skills.py`](src/skills.py): `load_skills`, `catalog`, and the `Skill` tool (L1 scan at startup, L2 body-on-invoke). The only skill-specific code.
- `skills/<name>/SKILL.md`: sample skills, one with a bundled `reference.md` (the L3 resource).
- [`loop.py`](src/loop.py): unchanged, because a skill is just another tool.
- [`test.py`](src/test.py): walks the levels (L1 catalog scan, L2 body on invoke, L3 bundled file on disk for the file tool).

```bash
python sections/07-skills/src/test.py         # offline checks, no key
uv run python sections/07-skills/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `skills/loadSkillsDir.ts`, `skills/bundledSkills.ts`, `skills/mcpSkillBuilders.ts`, `tools/SkillTool/SkillTool.ts`, `tools/SkillTool/prompt.ts`.
- [Anthropic Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices): progressive disclosure levels.
- learn-claude-code · s07_skill_loading: section framing.
