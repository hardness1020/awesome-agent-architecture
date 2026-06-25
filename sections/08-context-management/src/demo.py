"""Section 8 demo: the loop with context.manage wired in, against the Anthropic
API. Offline checks live in test.py.

    uv run python sections/08-context-management/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run
from permissions import DEFAULT
from tools import Registry, Tool

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("08 context: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(Tool("ReadDoc", lambda a: "lorem ipsum " * 80, description="Read the project doc.",
                      is_read_only=True))
    answer = run("Read the project doc, then summarize it in one line.",
                 model, reg, Session(mode=DEFAULT), summarizer=lambda ms: "earlier: read the doc")
    print("08 context ->", answer)


if __name__ == "__main__":
    demo()
