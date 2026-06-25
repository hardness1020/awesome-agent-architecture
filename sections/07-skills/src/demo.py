"""Section 7 demo: loading a skill body on invoke, against the Anthropic API.
Offline checks live in test.py.

    uv run python sections/07-skills/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run
from permissions import DEFAULT
from skills import load_skills, skill_tool
from tools import Registry

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SKILLS_DIR = Path(__file__).resolve().parent / "skills"   # Claude Code scans .claude/skills


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("07 skills: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(skill_tool(load_skills(SKILLS_DIR)))   # L2; the agent's Read tool would do L3
    answer = run("Use the pdf-fill skill and tell me step 1.", model, reg, Session(mode=DEFAULT))
    print("07 skills ->", answer)


if __name__ == "__main__":
    demo()
