"""Section 6 offline checks: the Agent tool's shape, isolation, and recursion fence.
No key, no network.

    python sections/06-subagents/src/test.py
"""
from loop import Session
from permissions import DEFAULT
from subagents import agent_tool
from tools import Registry, Tool


def test():
    parent_session = Session(mode=DEFAULT)

    child_reg = Registry()                          # curated child tools: no Agent -> no recursion
    child_reg.register(Tool("CountFiles", lambda a: "3",
                            description="Count the python files in the repo.", is_read_only=True))
    parent_reg = Registry()                         # parent can ONLY delegate; it has no CountFiles
    parent_reg.register(agent_tool(lambda m, r: None, child_reg, parent_session))   # model unused here

    agent = parent_reg.get("Agent")
    assert agent is not None and agent.is_read_only
    assert "description" in agent.input_schema["properties"]
    assert child_reg.get("Agent") is None           # recursion fenced by tool curation
    assert parent_reg.get("CountFiles") is None      # context isolated: parent lacks the child's tools

    print("06 subagents: ok")


if __name__ == "__main__":
    test()
