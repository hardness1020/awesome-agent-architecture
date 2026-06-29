"""Skills (section 7): progressive disclosure of a skill into context.

Introduced in section 7, then carried forward unchanged.

A skill reveals itself in three levels, each loaded only when needed:
  L1 metadata  : name + description (frontmatter), always in the catalog (cheap).
  L2 body      : the SKILL.md instructions, read on invoke (skill_tool).
  L3 resources : files bundled in the skill folder. The body points to them and
                 the agent reads them with its normal file tools (Read / Bash),
                 not a skill-specific tool, on demand.
load_skills() scans the dir and keeps only L1; skill_tool reads L2 from disk on
invoke. Mirrors Claude Code's loadSkillsDir (scans .claude/skills) + SkillTool;
L3 reads go through the agent's Read tool, path-scoped by resolveSkillFilePath.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools import Tool

MAX_LISTING_DESC_CHARS = 80   # per-entry cap keeps the catalog cheap (Claude Code uses 250)

NAME_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}


@dataclass
class Skill:
    name: str
    description: str       # L1: from frontmatter, shown in the catalog
    path: Path            # SKILL.md; the body (L2) and bundled files (L3) are read on demand


def load_skills(skills_dir) -> list[Skill]:
    """L1: scan <skills_dir>/<name>/SKILL.md, keeping frontmatter only (cheap)."""
    skills = []
    for sub in sorted(Path(skills_dir).iterdir()):
        md = sub / "SKILL.md"
        if md.is_file():
            meta, _body = _split(md.read_text())
            skills.append(Skill(meta.get("name", sub.name), meta.get("description", ""), md))
    return skills


def catalog(skills) -> str:
    """L1: one line per skill, name + (truncated) description. Always-on, cheap."""
    return "\n".join(f"- {s.name}: {s.description[:MAX_LISTING_DESC_CHARS]}" for s in skills)


def skill_tool(skills) -> Tool:
    """L2: read one skill's body from disk into the conversation on invoke."""
    by_name = {s.name: s for s in skills}

    def load(a):
        skill = by_name.get(a["name"])
        if skill is None:
            raise KeyError(f"no skill {a['name']!r}")   # invoke by registered name, never a raw path
        _meta, body = _split(skill.path.read_text())
        return body                                       # tool result -> enters messages[]

    description = "Load a skill body by name. Available:\n" + catalog(skills)
    return Tool("Skill", load, description=description, input_schema=NAME_SCHEMA, is_read_only=True)


def _split(text):
    """Minimal SKILL.md parse into (frontmatter dict, body). ponytail: assumes a
    well-formed '---\\n<key: value>...\\n---\\n<body>' header (real CC uses YAML)."""
    _, frontmatter, body = text.split("---", 2)
    meta = {k.strip(): v.strip() for k, v in
            (line.split(":", 1) for line in frontmatter.strip().splitlines() if ":" in line)}
    return meta, body.strip()
