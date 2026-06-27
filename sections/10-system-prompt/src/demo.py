"""Section 10 demo: the system prompt re-assembled from live state each turn,
against the Anthropic API. Offline checks live in test.py.

    uv run python sections/10-system-prompt/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from prompt import DEMO_SECTIONS, assemble
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("10 prompt: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024,
                                       cache_control={"type": "ephemeral"})   # automatic: cache system + growing messages

    def assemble_prompt(registry, session):                # re-run every turn from live state
        state = {"tools": [s["name"] for s in registry.schemas()], "cwd": os.getcwd()}
        return assemble(DEMO_SECTIONS, state)              # full prompt string; the top-level cache_control caches it

    reg = Registry()
    reg.register(Tool("Ping", lambda a: "pong", description="Return pong.", is_read_only=True))
    
    # automatic caching (top-level cache_control) caches the whole system prompt plus the growing
    # messages, advancing as the conversation grows. This prompt is far under the 1024-token minimum,
    # so it shows where caching is enabled, not a live hit.
    answer = run_turn([{"role": "user", "content": "Call Ping, then tell me which tools your prompt said you have."}],
                 model, reg, Session(mode=DEFAULT), prompt=assemble_prompt)
    print("10 prompt ->", answer)


if __name__ == "__main__":
    demo()
