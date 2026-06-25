"""Section 4 offline checks: a PreToolUse hook blocks a call before the gate. No key, no network.

    python sections/04-hooks/src/test.py
"""
from types import SimpleNamespace

from hooks import POST_TOOL_USE, PRE_TOOL_USE, Hooks
from loop import _dispatch
from permissions import BYPASS
from tools import Registry, Tool


def build():
    reg = Registry()
    reg.register(Tool("Bash", lambda a: "ran", description="Run a shell command.",
                      input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                                    "required": ["command"]}))
    hooks = Hooks()
    log = []
    hooks.on(PRE_TOOL_USE, lambda n, a: {"deny": True, "message": "refusing rm -rf"}
             if n == "Bash" and "rm -rf" in a.get("command", "") else None)
    hooks.on(POST_TOOL_USE, lambda n, a, r: log.append(n))
    return reg, hooks, log


def _bash(reg, hooks, command):
    block = SimpleNamespace(type="tool_use", id="t", name="Bash", input={"command": command})
    return _dispatch(block, reg, hooks, BYPASS, set(), lambda n, a: False)["content"]


def test():
    reg, hooks, log = build()

    # BYPASS would allow the call, but the PreToolUse hook blocks it first
    assert _bash(reg, hooks, "rm -rf /") == "refusing rm -rf"
    assert log == []                       # a blocked call never reaches PostToolUse

    assert _bash(reg, hooks, "ls") == "ran"
    assert log == ["Bash"]                 # the allowed call did reach PostToolUse

    print("04 hooks: ok")


if __name__ == "__main__":
    test()
