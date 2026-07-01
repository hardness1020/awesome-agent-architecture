"""Section 20 demo: telemetry watches one live turn, then an offline eval scores.

The loop does not change. Telemetry rides the model wrapper from outside: each
model call emits an event and adds its token usage to the CostTracker, so the
run is reconstructable and its spend is known without touching run_turn. A sink
prints every event; the session cost prints at the end.

There is one run_turn in demo() (the observed loop). After it, run_eval replays
a small fixed task set against a local build and grades it, showing the second,
offline pipeline: telemetry says what happened, eval says whether it was good.

    uv run python sections/20-observability/src/demo.py   (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from telemetry import CostTracker, Telemetry, run_eval
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = "Use the add tool to compute sums. Answer with just the number, no preamble."

ADD = Tool(name="add", run=lambda a: a["x"] + a["y"], description="Add two integers.",
           input_schema={"type": "object",
                         "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                         "required": ["x", "y"]},
           is_read_only=True)


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("20 obs: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)
    tel = Telemetry()
    tel.attach(lambda name, meta: print("20 obs event:", name, meta))   # a printing sink
    cost = CostTracker()

    def model(messages, registry, system):
        r = client.messages.create(model=MODEL, system=system, messages=messages,
                                   tools=registry.schemas(), max_tokens=256)
        u = r.usage
        cost.add(MODEL, u.input_tokens, u.output_tokens)                # cost-tracker.ts rollup
        tel.emit("model_call", model=MODEL, tokens=u.input_tokens + u.output_tokens,
                 cost_usd=round(cost.cost_usd, 6))                      # analytics logEvent, scrubbed
        return r

    reg = Registry()
    reg.register(ADD)

    # The one observed agent call. Telemetry rides the model wrapper; run_turn is unchanged.
    answer = run_turn([{"role": "user", "content": "What is 27 + 15? Use the add tool."}],
                      lambda m, r, s: model(m, r, SYSTEM), reg,
                      Session(mode=DEFAULT, allow_rules=set()))
    print("20 obs:", answer)
    print("20 obs: session cost $%.6f, usage %s" % (cost.cost_usd, cost.by_model))

    # The offline pipeline: replay a fixed task set against a local build and grade it.
    build = lambda inp: inp["a"] + inp["b"]
    tasks = [({"a": 27, "b": 15}, lambda o: o == 42), ({"a": 2, "b": 2}, lambda o: o == 4)]
    print("20 obs: eval", run_eval(build, tasks))


if __name__ == "__main__":
    demo()
