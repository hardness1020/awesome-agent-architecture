"""Section 7 offline checks: progressive disclosure across three levels, then
the store evolving (usage record, staleness, agent-written skill).
No key, no network.

    python sections/07-skills/src/test.py
"""
import json
import shutil
import tempfile
from pathlib import Path

from skills import (USAGE_FILE, catalog_prompt, load_skills, read_tool,
                    stale_skills, write_skill, write_tool)
from tools import run_tool

BUNDLED = Path(__file__).resolve().parent / "skills"


def test():
    # work on a throwaway copy: reads bump a usage record, and the store may grow
    SKILLS_DIR = Path(tempfile.mkdtemp()) / "skills"
    shutil.copytree(BUNDLED, SKILLS_DIR)

    skills = load_skills(SKILLS_DIR)
    by_name = {s.name: s for s in skills}
    assert {"pdf-fill", "sql-style"} <= set(by_name)            # L1: discovered from disk

    prompt = catalog_prompt(skills, SKILLS_DIR)                 # L1: catalog rides in the system prompt
    assert "pdf-fill" in prompt                                 # name is listed
    assert "pdf-fill/SKILL.md" in prompt                        # with the path to read
    assert "PDF FILL STEPS" not in prompt                       # but never the body
    assert len(prompt) < sum(len(s.path.read_text()) for s in skills)

    read = read_tool(SKILLS_DIR)                                # the normal file tool; no skill-specific tool
    body = read.run({"path": "pdf-fill/SKILL.md"})             # L2: whole file read on demand
    assert "PDF FILL STEPS:" in body                           # instructions are in the file

    # L3: the body points to a bundled file; the SAME Read tool loads it on demand.
    assert "reference.md" in body and "email_addr" not in body
    ref = read.run({"path": "pdf-fill/reference.md"})
    assert "email_addr" in ref                                  # the resource loads by path

    # path traversal is rejected; the name can never escape the skills dir.
    assert run_tool(read, {"path": "../../../../etc/passwd"}).startswith("error:")

    # use: reading a SKILL.md bumped the usage record (resource reads do not)
    usage = json.loads((SKILLS_DIR / USAGE_FILE).read_text())
    assert usage["pdf-fill"]["uses"] == 1 and "sql-style" not in usage

    # curate: the unused skill is stale; the just-used one is not
    assert stale_skills(SKILLS_DIR, skills, now=usage["pdf-fill"]["last_used_at"] + 1) == ["sql-style"]

    # write: the agent saves a new skill; the next scan catalogs it
    write = write_tool(SKILLS_DIR)
    write.run({"name": "csv-clean", "description": "Clean a CSV export.", "body": "1. strip BOM"})
    grown = load_skills(SKILLS_DIR)
    assert "csv-clean" in {s.name for s in grown}
    assert "csv-clean" in catalog_prompt(grown, SKILLS_DIR)
    try:                                                    # a written name cannot escape either
        write_skill(SKILLS_DIR, "../evil", "d", "b")
        assert False, "traversal accepted"
    except ValueError:
        pass

    print("07 skills: ok")


if __name__ == "__main__":
    test()
