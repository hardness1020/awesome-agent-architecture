"""Section 4 demo: hooks around tool calls, against the Anthropic API. Offline
checks live in test.py.

    uv run python sections/04-hooks/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from hooks import PRE_TOOL_USE, Hooks
from loop import run
from permissions import BYPASS
from tools import Registry, Tool

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("04 hooks: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(Tool("Bash", lambda a: "ran", description="Run a shell command.",
                      input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                                    "required": ["command"]}))
    hooks = Hooks()
    hooks.on(PRE_TOOL_USE, lambda n, a: {"deny": True, "message": "refusing rm -rf"}
             if n == "Bash" and "rm -rf" in a.get("command", "") else None)
    answer = run("Run the shell command: echo hello", model, reg, hooks=hooks, mode=BYPASS)
    print("04 hooks ->", answer)


if __name__ == "__main__":
    demo()
