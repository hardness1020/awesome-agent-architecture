"""Section 4 self-check: a PreToolUse hook blocks a dangerous command even
under bypassPermissions, and a blocked call never reaches PostToolUse. No API key.

    python sections/04-hooks/src/demo.py
"""
from hooks import POST_TOOL_USE, PRE_TOOL_USE, Hooks
from loop import run
from permissions import BYPASS
from tools import Registry, Tool


def stub_model(messages, registry):
    ran = [m for m in messages if m.get("role") == "tool"]
    if not ran:
        return {"stop_reason": "tool_use", "text": "",
                "tool_calls": [{"name": "Bash", "args": {"command": "rm -rf /"}}]}

    return {"stop_reason": "end_turn", "tool_calls": [], "text": ran[0]["status"]}


def demo():
    reg = Registry()
    reg.register(Tool("Bash", lambda a: "ran"))

    hooks = Hooks()
    log = []
    hooks.on(PRE_TOOL_USE, lambda n, a: {"deny": True, "message": "refusing rm -rf"}
             if n == "Bash" and "rm -rf" in a.get("command", "") else None)
    hooks.on(POST_TOOL_USE, lambda n, a, r: log.append(n))

    # BYPASS would allow the call, but the PreToolUse hook blocks it first
    assert run("danger", stub_model, reg, hooks=hooks, mode=BYPASS) == "blocked"
    assert log == []   # a blocked call never reaches PostToolUse
    print("04 hooks: ok")


if __name__ == "__main__":
    demo()
