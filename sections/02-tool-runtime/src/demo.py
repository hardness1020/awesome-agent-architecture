"""Section 2 demo: the loop dispatching tool calls through a Registry, against
the Anthropic API. Offline checks live in test.py.

    uv run python sections/02-tool-runtime/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import run_turn
from tools import Registry, Tool

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
FILES = {"a.txt": "alpha", "b.txt": "beta"}


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("02 tool_runtime: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(Tool("ReadFile", lambda a: FILES[a["path"]],
                      description="Read a file's contents by path.",
                      input_schema={"type": "object", "properties": {"path": {"type": "string"}},
                                    "required": ["path"]},
                      is_read_only=True, is_concurrency_safe=True))
    
    answer = run_turn([{"role": "user", "content": "Read a.txt and b.txt, then reply with both contents."}], model, reg)
    print("02 tool_runtime ->", answer)


if __name__ == "__main__":
    demo()
