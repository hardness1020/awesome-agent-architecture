"""Section 6 demo: delegating to a subagent, against the Anthropic API. Offline
checks live in test.py.

    uv run python sections/06-subagents/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from subagents import agent_tool
from tools import Registry, Tool

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("06 subagents: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    parent_session = Session(mode=DEFAULT)
    child_reg = Registry()                          # curated child tools: no Agent -> no recursion
    child_reg.register(Tool("CountFiles", lambda a: "there are 3 python files",
                            description="Count the python files in the repo.", is_read_only=True))
    parent_reg = Registry()                         # parent can ONLY delegate
    parent_reg.register(agent_tool(model, child_reg, parent_session))
    
    answer = run_turn([{"role": "user", "content": "Use the Agent tool to count the python files, then report the number."}],
                 model, parent_reg, parent_session)
    print("06 subagents ->", answer)


if __name__ == "__main__":
    demo()
