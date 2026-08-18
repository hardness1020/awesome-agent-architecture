"""Spill store (section 8): the deepseek-harness contrast to `_budget`.

`_budget` in context.py cuts an oversized tool result down to a preview, and the
rest is gone. A spill store writes the full text to a session file first, then
leaves a head and tail preview plus the path in context. The model can read the
file back with the tools it already has.

This is a contrast demo. It is not wired into context.manage(), so later sections
carry the same context passes forward.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

MAX_INLINE_CHARS = 400   # a result longer than this spills
PREVIEW_CHARS = 60       # kept verbatim at each end


class SpillStore:
    """Saves text under one session directory and returns the path to it."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or tempfile.mkdtemp(prefix="spill-"))
        self.root.mkdir(parents=True, exist_ok=True)

    def save_text(self, text: str) -> str:
        path = self.root / (hashlib.sha256(text.encode()).hexdigest()[:16] + ".txt")
        path.write_text(text)     # ponytail: no private file mode; add one when the root leaves a temp dir
        return str(path)


def spill_results(messages, store: SpillStore) -> None:
    """Persist every oversized tool result; leave a preview and a retrieval hint."""
    for m in messages:
        content = m.get("content")
        if m.get("role") != "user" or not isinstance(content, list):
            continue
        for block in content:
            body = block.get("content") if isinstance(block, dict) else None
            if block.get("type") == "tool_result" and isinstance(body, str) and len(body) > MAX_INLINE_CHARS:
                block["content"] = _preview(body, store.save_text(body))


def _preview(text: str, path: str) -> str:
    return (f"{text[:PREVIEW_CHARS]} ...[{len(text)} chars spilled]... {text[-PREVIEW_CHARS:]}\n"
            f'<spilled path="{path}"> Read or grep this file for the full output.')
