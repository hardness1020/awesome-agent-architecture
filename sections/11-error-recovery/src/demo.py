"""Section 11 demo: the loop recovering from a simulated overload, against the
Anthropic API. Offline checks live in test.py.

The first model call raises a fake 529; with_retry backs off and retries, and
the second call hits the real API. So a live run visibly recovers.

    uv run python sections/11-error-recovery/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = "You are a tiny agent. Be brief."


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("11 recovery: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)
    state = {"overloaded": False}

    def model(messages, registry, system):
        if not state["overloaded"]:
            state["overloaded"] = True                     # fail once, then succeed
            err = Exception("simulated overload")
            err.status_code = 529
            raise err                                      # the loop's with_retry backs off and retries
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(Tool("Ping", lambda a: "pong", description="Return pong.", is_read_only=True))
    
    answer = run_turn([{"role": "user", "content": "Say hello in five words."}], model, reg, Session(mode=DEFAULT))
    print("11 recovery -> (recovered from a 529)", answer)


if __name__ == "__main__":
    demo()
