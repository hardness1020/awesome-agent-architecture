"""Section 21 demo: one verified run. A worker answers, a separate checker
grades it against a fixed rubric, and the harness retries with feedback or
escalates at the budget.

verified_run wraps run_turn from outside; the inner loop is unchanged. The
checker is its own agent on a fresh messages[] (section 6), so the worker
never grades its own output. A section-14 trigger could start this run
instead of the script; the verification loop is the same either way.

    uv run python sections/21-loop-engineering/src/demo.py   (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from tools import Registry, Tool
from verify import agent_checker, verified_run

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
RUBRIC = "The output is exactly one number and nothing else."

ADD = Tool(name="add", run=lambda a: a["x"] + a["y"], description="Add two integers.",
           input_schema={"type": "object",
                         "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                         "required": ["x", "y"]},
           is_read_only=True)


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("21 loop-eng: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        kwargs = {"system": system} if system else {}
        return client.messages.create(model=MODEL, messages=messages,
                                      tools=registry.schemas(), max_tokens=256, **kwargs)

    reg = Registry()
    reg.register(ADD)

    def worker(prompt):                            # the inner loop, unchanged (section 1)
        return run_turn([{"role": "user", "content": prompt}], model, reg, Session(mode=DEFAULT))

    checker = agent_checker(RUBRIC, model)         # a fresh grader agent, no tools (section 6)

    result = verified_run("What is 27 + 15? Use the add tool. Answer with just the number.",
                          worker, checker, budget=2)
    for a in result["attempts"]:
        print(f"21 loop-eng: attempt {a['attempt']}: "
              f"{'PASS' if a['passed'] else 'FAIL'} · {a['reason']}")
    print("21 loop-eng:", result["output"] if result["ok"] else "budget spent, escalating to a human")


if __name__ == "__main__":
    demo()
