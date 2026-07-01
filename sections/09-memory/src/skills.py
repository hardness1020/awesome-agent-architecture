"""Skills (section 7): progressive disclosure of a skill into context.

Introduced in section 7, then carried forward unchanged.

A skill reveals itself in three levels, each loaded only when needed:
  L1 metadata  : name + description (frontmatter), always in the system prompt (cheap).
  L2 body      : the SKILL.md instructions, read on demand with the normal file tool.
  L3 resources : files bundled in the skill folder, read with the same file tool.

No skill-specific tool is needed. Once the catalog (name, description, path) sits
in the system prompt, the agent loads a skill by reading its SKILL.md with the same
Read tool it uses for any file. L2 (body) and L3 (resources) both go through that
one tool. load_skills() scans the dir and keeps only L1; catalog_prompt() renders
the L1 block for the system prompt. Mirrors Claude Code's loadSkillsDir (scans
.claude/skills) and its system-prompt skill listing. Claude Code wraps body-loading
in a SkillTool because its skills also fork and scope tools; the plain mechanism
here does not need one, so a normal path-scoped Read does the job.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools import Tool

MAX_LISTING_DESC_CHARS = 80   # per-entry cap keeps the catalog cheap (Claude Code uses 250)

PATH_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
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


def catalog_prompt(skills, base_dir) -> str:
    """L1: the skills block injected into the system prompt at startup, so the model
    knows which skills exist and where to read each one. Name + description + path
    only, never the body. The agent reads the path with its normal Read tool."""
    base = Path(base_dir)
    lines = [f"- {s.name}: {s.description[:MAX_LISTING_DESC_CHARS]} (read {s.path.relative_to(base)})"
             for s in skills]
    return "Available skills (read a skill's path with the Read tool to load it):\n" + "\n".join(lines)


def read_tool(base_dir) -> Tool:
    """The normal file tool. Loads a skill body (L2) or a bundled resource (L3) by
    path. Scoped to base_dir so a skill name can never escape into the filesystem."""
    base = Path(base_dir).resolve()

    def read(a):
        target = (base / a["path"]).resolve()
        if not target.is_relative_to(base):          # reject path traversal (../../etc/passwd)
            raise ValueError(f"path {a['path']!r} escapes the skills dir")
        return target.read_text()                     # tool result -> enters messages[]

    return Tool("Read", read, description="Read a file by its path.",
                input_schema=PATH_SCHEMA, is_read_only=True)


def _split(text):
    """Minimal SKILL.md parse into (frontmatter dict, body). ponytail: assumes a
    well-formed '---\\n<key: value>...\\n---\\n<body>' header (real CC uses YAML)."""
    _, frontmatter, body = text.split("---", 2)
    meta = {k.strip(): v.strip() for k, v in
            (line.split(":", 1) for line in frontmatter.strip().splitlines() if ":" in line)}
    return meta, body.strip()
