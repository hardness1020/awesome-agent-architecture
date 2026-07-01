"""Section 7 offline checks: progressive disclosure across three levels.
No key, no network.

    python sections/07-skills/src/test.py
"""
from pathlib import Path

from skills import catalog_prompt, load_skills, read_tool
from tools import run_tool

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def test():
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

    print("07 skills: ok")


if __name__ == "__main__":
    test()
