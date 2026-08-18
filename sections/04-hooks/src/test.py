"""Section 4 offline checks: a PreToolUse hook blocks a call before the gate. No key, no network.

    python sections/04-hooks/src/test.py
"""
from types import SimpleNamespace

from hooks import POST_TOOL_USE, PRE_TOOL_USE, Hooks
from loop import _dispatch
from permissions import BYPASS
from tools import Registry, Tool
from waterfall import ALLOW, ASK, DENY, Waterfall, merge


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


def test_waterfall():
    pre = Waterfall()
    seen = []

    def audit(call, next):
        out = next()                       # delegate, then wrap: record the outcome
        seen.append((call["name"], out))
        return out

    def guard(call, next):
        if "rm -rf" in call["args"].get("command", ""):
            return DENY                    # owns the decision: no next()
        return next()

    pre.on(audit)
    pre.on(guard)

    assert pre.dispatch({"name": "Bash", "args": {"command": "rm -rf /"}}) == DENY
    assert pre.dispatch({"name": "Bash", "args": {"command": "ls"}}) == ALLOW  # chain end: default
    assert seen == [("Bash", DENY), ("Bash", ALLOW)]   # the wrapper saw both outcomes

    assert merge([ALLOW, ASK, DENY]) == DENY           # most restrictive wins
    assert merge([DENY, ASK, ALLOW]) == DENY           # ordering cannot loosen it
    assert merge([ASK, ALLOW]) == ASK
    assert merge([]) == ALLOW

    print("04 waterfall: ok")


if __name__ == "__main__":
    test()
    test_waterfall()
