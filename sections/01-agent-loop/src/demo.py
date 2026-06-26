"""Section 1 demo: a two-turn conversation over one persistent messages[],
against the Anthropic API. Offline checks live in test.py.

    uv run python sections/01-agent-loop/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import TOOL_SCHEMAS, run_turn

load_dotenv(override=True)

SYSTEM = "You are a tiny agent. Use the provided tools to answer. Be brief."
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

TURNS = [
    "What time is it right now? Answer in one sentence.",
    "Was that before or after noon, UTC?",        # only answerable if turn 1 is still in context
]


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("01 agent_loop: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages):                          # the injected model; swap it, keep run_turn()
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=TOOL_SCHEMAS, max_tokens=1024)

    messages = []                                 # the conversation, owned here and reused every turn
    for user_text in TURNS:
        messages.append({"role": "user", "content": user_text})
        reply = run_turn(messages, model)         # appends in place; turn 2 sees turn 1 verbatim
        print("you ->", user_text)
        print("01 agent_loop ->", reply)


if __name__ == "__main__":
    demo()
