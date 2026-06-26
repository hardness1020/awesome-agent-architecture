"""Section 5 demo: planning / plan mode, against the Anthropic API. Offline
checks live in test.py.

    uv run python sections/05-planning-todos/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from planning import todo_tool
from tools import Registry

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("05 planning: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    session = Session(mode=DEFAULT)
    reg = Registry()
    reg.register(todo_tool(session))
    
    answer = run_turn([{"role": "user", "content": "Make a 2-step todo list for cleaning a kitchen, then say done."}],
                 model, reg, session)
    print("05 planning ->", answer, "| todos:", len(session.todos))


if __name__ == "__main__":
    demo()
