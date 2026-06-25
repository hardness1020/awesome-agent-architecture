"""Section 6 self-check: the parent delegates a subproblem to a child loop and
gets back only the child's one-line conclusion. The child's own tool call
(CountFiles) runs in the child's context and never enters the parent's. No API key.

    python sections/06-subagents/src/demo.py
"""
from loop import Session, run
from permissions import DEFAULT
from subagents import agent_tool
from tools import Registry, Tool

PARENT_INTENT = "summarize the repo"
CHILD_TASK = "count the python files"


def model(messages, registry, session):
    """One stub serving both loops; it branches on the seed (messages[0])."""
    seed = messages[0]["content"]
    turns = sum(1 for m in messages if m["role"] == "assistant")

    if seed == PARENT_INTENT:                       # parent context
        if turns == 0:
            return _call("Agent", {"description": CHILD_TASK})
        return _done(f"repo summary: {_last_tool(messages)}")    # only the child's conclusion is here

    if turns == 0:                                  # child context (seed == CHILD_TASK)
        return _call("CountFiles", {})
    return _done("3 python files")


def _call(name, args):
    return {"stop_reason": "tool_use", "text": "", "tool_calls": [{"name": name, "args": args}]}


def _done(text):
    return {"stop_reason": "end_turn", "text": text, "tool_calls": []}


def _last_tool(messages):
    return next(m["content"] for m in reversed(messages) if m["role"] == "tool")


def demo():
    parent_session = Session(mode=DEFAULT)
    child_did = []

    def count_files(_a):
        child_did.append("CountFiles")
        return "3"

    child_reg = Registry()                          # curated child tools: no Agent -> no recursion
    child_reg.register(Tool("CountFiles", count_files, is_read_only=True))

    parent_reg = Registry()                         # parent can ONLY delegate; it has no CountFiles
    parent_reg.register(agent_tool(model, child_reg, parent_session))

    out = run(PARENT_INTENT, model, parent_reg, parent_session)

    assert out == "repo summary: 3 python files", out
    assert child_did == ["CountFiles"]              # the work happened in the child
    assert parent_reg.get("CountFiles") is None     # ...not in the parent: context was isolated
    assert child_reg.get("Agent") is None           # recursion fenced by tool curation

    print("06 subagents: ok ->", out)


if __name__ == "__main__":
    demo()
