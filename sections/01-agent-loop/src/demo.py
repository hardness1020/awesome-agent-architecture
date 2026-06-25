"""Section 1 demo: the agent loop answering one question with a tool call,
against the Anthropic API. Offline checks live in test.py.

    uv run python sections/01-agent-loop/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import TOOL_SCHEMAS, run

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("01 agent_loop: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages):                          # the injected model; swap it, keep run()
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=TOOL_SCHEMAS, max_tokens=1024)

    answer = run("What time is it right now? Answer in one sentence.", model)
    print("01 agent_loop ->", answer)


if __name__ == "__main__":
    demo()
