"""Section 3 offline checks: the gate decisions and the gate inside dispatch. No key, no network.

    python sections/03-permission-sandbox/src/test.py
"""
from types import SimpleNamespace

from loop import _dispatch
from permissions import ACCEPT_EDITS, BYPASS, DEFAULT, PLAN, decide
from tools import Registry, Tool


def build_registry():
    reg = Registry()
    reg.register(Tool("ReadFile", lambda a: "data", description="Read a file by path.",
                      input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                      is_read_only=True))
    reg.register(Tool("Bash", lambda a: "ran", description="Run a shell command.",
                      input_schema={"type": "object", "properties": {"command": {"type": "string"}}}))
    reg.register(Tool("EditFile", lambda a: "edited", description="Edit a file.", is_edit=True))
    return reg


def _dispatch_content(reg, name, tool_input, mode):
    block = SimpleNamespace(type="tool_use", id=name, name=name, input=tool_input)
    return _dispatch(block, reg, mode, set(), lambda n, a: False)["content"]


def test():
    reg = build_registry()

    # the gate, mode by mode
    assert decide(reg.get("ReadFile"), PLAN, set()) == "allow"
    assert decide(reg.get("EditFile"), PLAN, set()) == "deny"
    assert decide(reg.get("EditFile"), ACCEPT_EDITS, set()) == "allow"
    assert decide(reg.get("Bash"), DEFAULT, set()) == "ask"
    assert decide(reg.get("Bash"), DEFAULT, {"Bash"}) == "allow"
    assert decide(reg.get("Bash"), BYPASS, set()) == "allow"

    # in the loop's dispatch: default mode, no approver -> read runs, bash denied
    assert _dispatch_content(reg, "ReadFile", {"path": "a"}, DEFAULT) == "data"
    assert _dispatch_content(reg, "Bash", {"command": "ls"}, DEFAULT) == "Bash denied by user"

    print("03 permissions: ok")


if __name__ == "__main__":
    test()
