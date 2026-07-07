"""Section 7 demo: loading a skill body on invoke, then the agent saving a new
skill from what it just did (skill evolution), against the Anthropic API.
Offline checks live in test.py.

    uv run python sections/07-skills/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import shutil
import tempfile
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from skills import catalog_prompt, load_skills, read_tool, write_tool
from tools import Registry

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
BUNDLED = Path(__file__).resolve().parent / "skills"   # Claude Code scans .claude/skills


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("07 skills: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    skills_dir = Path(tempfile.mkdtemp()) / "skills"    # throwaway copy: this store evolves
    shutil.copytree(BUNDLED, skills_dir)
    skills = load_skills(skills_dir)
    system = SYSTEM + "\n\n" + catalog_prompt(skills, skills_dir)   # L1 catalog rides in the system prompt

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=system, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(read_tool(skills_dir))                 # one file tool serves L2 (SKILL.md) and L3 (resources)
    reg.register(write_tool(skills_dir))                # ...and the agent can save a new skill

    answer = run_turn([{"role": "user", "content":
                        "Use the pdf-fill skill and tell me step 1. Then save a skill named "
                        "'pdf-step-one' that captures just that step for next time."}],
                      model, reg, Session(mode=DEFAULT, allow_rules={"WriteSkill"}))
    print("07 skills ->", answer)
    print("07 skills · store now:", sorted(s.name for s in load_skills(skills_dir)))   # it grew


if __name__ == "__main__":
    demo()
