"""Memory (section 9): a durable file store the agent recalls from and writes to.

Introduced in section 9, then carried forward unchanged.

messages[] dies with the run (section 1) and degrades under compaction
(section 8). Memory is the layer outside the conversation: small .md files with
frontmatter, recall that injects only the few relevant bodies into a turn, and
extraction that writes new files at run end. Four operations, never conflated:
  selection    : what is worth keeping. the type taxonomy gates the store, so
                 derivable facts (code, git) are never written.
  recall       : read-only, at query time. rank the index, inject a few bodies.
  extraction   : write-only, at run end. append new files.
  consolidation: rare, background (section 13). dedupe + prune. not shown here.
Mirrors Claude Code's memdir (findRelevantMemories, memoryScan) + extractMemories.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TYPES = ("user", "feedback", "project", "reference")   # non-derivable only; the rest is grep's job
RECALL_K = 5                                            # cap injected memories (precision over recall)


@dataclass
class Memory:
    name: str
    type: str          # one of TYPES
    description: str    # the cheap index line, ranked at recall time
    path: Path          # the .md file; its body is read only when recalled


def load_index(memory_dir) -> list[Memory]:
    """Scan <dir>/*.md, keeping frontmatter only. The cheap manifest, never the bodies."""
    mems = []
    for md in sorted(Path(memory_dir).glob("*.md")):
        if md.name == "MEMORY.md":          # the index file itself is not a memory
            continue
        meta, _body = _split(md.read_text())
        mems.append(Memory(md.stem, meta.get("type", ""), meta.get("description", ""), md))
    return mems


def manifest(mems) -> str:
    """One line per memory: name, type, description. Always-on and cheap (section 10)."""
    return "\n".join(f"- {m.name} ({m.type}): {m.description}" for m in mems)


def recall(mems, query, k=RECALL_K, selector=None) -> list[Memory]:
    """Pick the few memories relevant to `query`. `selector` is the live relevance
    judge (an LLM reading the manifest); without it, fall back to word overlap."""
    if selector is not None:
        chosen = set(selector(manifest(mems), query))     # LLM returns the names to inject
        return [m for m in mems if m.name in chosen][:k]
    scored = ((_overlap(query, m), m) for m in mems)
    hits = sorted((s for s in scored if s[0]), key=lambda s: s[0], reverse=True)
    return [m for _score, m in hits[:k]]


def recall_block(mems, query, k=RECALL_K, selector=None) -> str:
    """The recalled bodies, formatted for injection into a turn. '' if nothing fits."""
    hits = recall(mems, query, k, selector)
    return "\n\n".join(f"[memory · {m.type}] {_split(m.path.read_text())[1]}" for m in hits)


def extract(memory_dir, messages, extractor) -> list[Path]:
    """Run end: the extractor proposes new memories from the transcript; write each.
    The only operation that grows the store. extractor(messages) returns dicts of
    {name, type, description, body}; an empty list writes nothing."""
    written = []
    for m in extractor(messages) or []:
        path = Path(memory_dir) / f"{m['name']}.md"
        path.write_text(_render(m))
        written.append(path)
    return written


@dataclass
class Store:
    """The handle threaded into the loop (loop.py): recall before the run, extract
    after. `selector` / `extractor` are the live LLM hooks; both optional."""
    root: Path
    selector: Callable | None = None
    extractor: Callable | None = None

    def recall(self, query, k=RECALL_K) -> str:
        return recall_block(load_index(self.root), query, k, self.selector)

    def write(self, messages) -> list[Path]:
        return extract(self.root, messages, self.extractor) if self.extractor else []


def _overlap(query, mem) -> int:
    return len(_words(query) & _words(mem.name + " " + mem.description))


def _words(text) -> set:
    return {w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(w) > 2}


def _render(m) -> str:
    return f"---\ntype: {m['type']}\ndescription: {m['description']}\n---\n{m['body']}\n"


def _split(text):
    """Minimal frontmatter parse into (meta dict, body). Same shape as skills.py."""
    _, frontmatter, body = text.split("---", 2)
    meta = {k.strip(): v.strip() for k, v in
            (line.split(":", 1) for line in frontmatter.strip().splitlines() if ":" in line)}
    return meta, body.strip()
