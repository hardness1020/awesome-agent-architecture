"""Section 7 offline checks: progressive disclosure across three levels.
No key, no network.

    python sections/07-skills/src/test.py
"""
from pathlib import Path

from skills import catalog, load_skills, skill_tool

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def test():
    skills = load_skills(SKILLS_DIR)
    by_name = {s.name: s for s in skills}
    assert {"pdf-fill", "sql-style"} <= set(by_name)            # L1: discovered from disk

    cat = catalog(skills)                                       # L1: cheap catalog
    assert "pdf-fill" in cat
    assert len(cat) < sum(len(s.path.read_text()) for s in skills)

    body = skill_tool(skills).run({"name": "pdf-fill"})         # L2: body read on invoke
    assert body.startswith("PDF FILL STEPS:")

    # L3: the body points to a bundled file that sits on disk, separate from the
    # body. An agent reads it with its normal file tools (section 3), not here.
    assert "reference.md" in body and "email_addr" not in body
    assert (by_name["pdf-fill"].path.parent / "reference.md").is_file()

    print("07 skills: ok")


if __name__ == "__main__":
    test()
