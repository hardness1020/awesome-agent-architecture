"""Section 22 demo: one routed graph run. A code node classifies the task,
a coded edge routes it to a specialist, an agent node answers inside the
graph, a checker node grades it, and a failed verdict cycles back with
feedback until the step budget stops it.

run_turn is unchanged; nodes wrap it (section 1). The checker is section
21's agent_checker mounted as a node, so the evaluator-optimizer shape is
two nodes and one backward edge. Routing spends no tokens: the classify
node and every edge are plain code.

    uv run python sections/22-graph-engineering/src/demo.py   (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from graph import END, agent_node, run_graph
from tools import Registry, Tool
from verify import agent_checker

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
        print("22 graph-eng: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        kwargs = {"system": system} if system else {}
        return client.messages.create(model=MODEL, messages=messages,
                                      tools=registry.schemas(), max_tokens=256, **kwargs)

    math_reg = Registry()
    math_reg.register(ADD)
    prompt = lambda s: s["task"] + s["feedback"]
    check = agent_checker(RUBRIC, model)               # section 21's checker, now a node

    def check_node(state):
        v = check(state["task"], state["output"])
        fb = "" if v["passed"] else (f"\n\nA prior attempt was rejected by review.\n"
                                     f"Attempt:\n{state['output']}\nWhy it failed: {v['reason']}\n"
                                     f"Fix that and answer again.")
        return {"verdict": v, "feedback": fb}

    nodes = {
        "classify": lambda s: {"route": "math" if any(c.isdigit() for c in s["task"]) else "prose"},
        "math": agent_node(prompt, model, math_reg),   # a full agent run as one node
        "prose": agent_node(prompt, model, Registry()),
        "check": check_node,
    }
    edges = {
        "classify": lambda s: s["route"],              # a coded edge: routing costs no tokens
        "math": "check",
        "prose": "check",
        "check": lambda s: END if s["verdict"]["passed"] else s["route"],   # the cycle
    }

    r = run_graph(nodes, edges,
                  {"task": "What is 27 + 15? Use the add tool. Answer with just the number.",
                   "feedback": ""},
                  start="classify", budget=5)
    print("22 graph-eng: trace:", " -> ".join(r["trace"]))
    print("22 graph-eng:", r["state"]["output"] if r["ok"] else "budget spent, escalating to a human")


if __name__ == "__main__":
    demo()
