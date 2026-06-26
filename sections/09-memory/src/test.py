"""Section 9 offline checks: the four memory operations. No key, no network.

    python sections/09-memory/src/test.py
"""
import tempfile
from pathlib import Path

import memory


def _seed(root, name, type_, description, body):
    (root / f"{name}.md").write_text(f"---\ntype: {type_}\ndescription: {description}\n---\n{body}\n")


def test():
    root = Path(tempfile.mkdtemp())
    _seed(root, "style-tabs", "feedback", "User prefers tabs not spaces for indentation.", "Use tabs.")
    _seed(root, "deploy-fri", "project", "Never deploy on Fridays.", "Releases wait for Monday.")
    (root / "MEMORY.md").write_text("# index\n- style-tabs ...\n")

    mems = memory.load_index(root)
    by = {m.name for m in mems}
    assert {"style-tabs", "deploy-fri"} <= by              # selection: discovered from disk
    assert "MEMORY" not in by                              # the index file itself is not a memory

    cat = memory.manifest(mems)                            # cheap index
    assert len(cat) < sum(len(m.path.read_text()) for m in mems)

    # recall: word overlap picks the relevant memory and drops the rest (precision over recall)
    hits = memory.recall(mems, "what are my tabs and spaces settings?")
    assert [m.name for m in hits] == ["style-tabs"]
    block = memory.recall_block(mems, "tabs and spaces?")
    assert "Use tabs." in block and "Monday" not in block

    # extraction: writes a new file; the index grows
    extractor = lambda messages: [{"name": "wants-brief", "type": "feedback",
                                   "description": "User wants brief answers.", "body": "Be terse."}]
    written = memory.extract(root, [], extractor)
    assert written and written[0].name == "wants-brief.md"
    assert "wants-brief" in {m.name for m in memory.load_index(root)}

    print("09 memory: ok")


if __name__ == "__main__":
    test()
