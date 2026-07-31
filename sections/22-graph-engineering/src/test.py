"""Section 22 offline checks, no key, no network.

test_chain(): fixed edges run nodes in order; each node's updates merge into
the state the next node reads. A node with no edge ends the graph.

test_route(): a conditional edge routes on the state. The branch not taken
never runs, and the edge itself is plain code, no model call.

test_cycle_budget(): a check node that never passes cycles back to the
worker until the step budget stops it with ok=False. The ceiling is the
harness's range(), not the model's judgment (section 21).

test_agent_node(): agent_node runs the inner loop on a fresh messages[]
built from the state and merges its text back under one key.

    python sections/22-graph-engineering/src/test.py
"""
from graph import END, agent_node, run_graph


def test_chain():
    trace_state = run_graph(
        nodes={"a": lambda s: {"seen": s["seen"] + ["a"]},
               "b": lambda s: {"seen": s["seen"] + ["b"], "n": s["n"] + 1},
               "c": lambda s: {"seen": s["seen"] + ["c"]}},
        edges={"a": "b", "b": "c"},                    # c has no edge: the graph ends
        state={"seen": [], "n": 41},
        start="a")
    assert trace_state["ok"] and trace_state["trace"] == ["a", "b", "c"]
    assert trace_state["state"]["seen"] == ["a", "b", "c"]
    assert trace_state["state"]["n"] == 42             # b's update survived c's merge

    print("22 graph-eng: chain ok")


def test_route():
    ran = []

    def worker(name):
        return lambda s: (ran.append(name), {})[1]

    r = run_graph(
        nodes={"classify": lambda s: {"route": "math" if s["task"].isdigit() else "prose"},
               "math": worker("math"), "prose": worker("prose")},
        edges={"classify": lambda s: s["route"]},      # a coded edge: routes on state
        state={"task": "2742"},
        start="classify")
    assert r["ok"] and r["trace"] == ["classify", "math"]
    assert ran == ["math"]                             # the prose branch never ran

    print("22 graph-eng: route ok")


def test_cycle_budget():
    r = run_graph(
        nodes={"work": lambda s: {"output": "wrong"},
               "check": lambda s: {"passed": False}},
        edges={"work": "check",
               "check": lambda s: END if s["passed"] else "work"},   # the cycle
        state={},
        start="work", budget=5)
    assert r["ok"] is False                            # stopped at the ceiling
    assert r["trace"] == ["work", "check", "work", "check", "work"]

    print("22 graph-eng: cycle-budget ok")


class _Text:                                           # a stand-in Anthropic text block
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:                                            # a stand-in Anthropic Message
    def __init__(self, text):
        self.content = [_Text(text)]
        self.stop_reason = "end_turn"


def test_agent_node():
    seen = []

    def model(messages, registry, system):
        seen.append(list(messages))
        return _Msg("42")

    class _Reg:
        def schemas(self):
            return []

    node = agent_node(lambda s: s["task"], model, _Reg(), key="answer")
    updates = node({"task": "add 27 and 15"})
    assert updates == {"answer": "42"}
    assert len(seen[0]) == 1                           # a fresh messages[] per visit
    assert seen[0][0]["content"] == "add 27 and 15"    # the node sees only its prompt

    print("22 graph-eng: agent-node ok")


if __name__ == "__main__":
    test_chain()
    test_route()
    test_cycle_budget()
    test_agent_node()
