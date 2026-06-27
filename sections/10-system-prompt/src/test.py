"""Section 10 offline checks: state-driven assembly. No key, no network.

    python sections/10-system-prompt/src/test.py
"""
from prompt import DEMO_SECTIONS, assemble

SEC = DEMO_SECTIONS


def test():
    base = {"tools": ["Read", "Ping"]}
    turn1 = dict(base)                                      # no cwd, no mcp
    turn2 = dict(base, cwd="/repo")                         # env section present this turn
    turn3 = dict(base, cwd="/repo", mcp=True)               # an mcp server connected this turn

    p1, p2, p3 = assemble(SEC, turn1), assemble(SEC, turn2), assemble(SEC, turn3)

    # included by state, not keywords: dynamic sections appear only when state has them
    assert "cwd:" not in p1
    assert "cwd: /repo" in p2
    assert "MCP servers" in p3 and "MCP servers" not in p2

    # recalled memory is NOT a system section; it rides in the message (section 9)
    assert "Recalled memory" not in p3

    # a section returning None is dropped, never rendered as the string "None"
    assert "None" not in p1

    # only the state-driven tail moves; the static head and the tools section stay put
    assert p1 != p2 != p3
    assert "Ping" in p1 and "Ping" in p3

    print("10 prompt: ok")


if __name__ == "__main__":
    test()
