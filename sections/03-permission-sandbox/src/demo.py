"""Section 3 self-check: the gate decisions mode by mode, then the gate in
the loop (a read allowed, a bash denied without an approver). No API key.

    python sections/03-permission-sandbox/src/demo.py
"""
from loop import run
from permissions import ACCEPT_EDITS, BYPASS, DEFAULT, PLAN, decide
from tools import Registry, Tool


def stub_model(messages, registry):
    ran = [m for m in messages if m.get("role") == "tool"]
    if not ran:
        return {"stop_reason": "tool_use", "text": "",
                "tool_calls": [{"name": "ReadFile", "args": {"path": "a"}},
                               {"name": "Bash", "args": {"command": "ls"}}]}

    return {"stop_reason": "end_turn", "tool_calls": [],
            "text": " | ".join(f"{m['name']}:{m['status']}" for m in ran)}


def demo():
    reg = Registry()
    reg.register(Tool("ReadFile", lambda a: "data", is_read_only=True))
    reg.register(Tool("Bash", lambda a: "ran"))
    reg.register(Tool("EditFile", lambda a: "edited", is_edit=True))

    # the gate, mode by mode
    assert decide(reg.get("ReadFile"), PLAN, set()) == "allow"
    assert decide(reg.get("EditFile"), PLAN, set()) == "deny"
    assert decide(reg.get("EditFile"), ACCEPT_EDITS, set()) == "allow"
    assert decide(reg.get("Bash"), DEFAULT, set()) == "ask"
    assert decide(reg.get("Bash"), DEFAULT, {"Bash"}) == "allow"
    assert decide(reg.get("Bash"), BYPASS, set()) == "allow"

    # in the loop: default mode, no approver -> read allowed, bash denied
    assert run("do stuff", stub_model, reg, mode=DEFAULT) == "ReadFile:ok | Bash:denied"
    print("03 permissions: ok")


if __name__ == "__main__":
    demo()
