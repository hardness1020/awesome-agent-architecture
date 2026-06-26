"""Section 3 demo: the permission gate inside the loop, against the Anthropic
API. Offline checks live in test.py.

    uv run python sections/03-permission-sandbox/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import run_turn
from permissions import DEFAULT
from tools import Registry, Tool

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("03 permissions: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(Tool("ReadFile", lambda a: "data", description="Read a file by path.",
                      input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                      is_read_only=True))
    answer = run_turn([{"role": "user", "content": "Read the file a.txt and summarize it."}], model, reg, mode=DEFAULT)
    print("03 permissions ->", answer)


if __name__ == "__main__":
    demo()
