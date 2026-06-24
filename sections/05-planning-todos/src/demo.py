"""Section 5 self-check: the full pipeline (1 to 5). The agent starts in plan
mode, drafts todos, is denied an edit, exits plan mode (human approves), the
edit lands under acceptEdits, and a dangerous command is hook-blocked. No API key.

    python sections/05-planning-todos/src/demo.py
"""
from hooks import POST_TOOL_USE, PRE_TOOL_USE, Hooks
from loop import Session, run
from permissions import ACCEPT_EDITS, PLAN
from planning import exit_plan_mode_tool, todo_tool
from tools import Registry, Tool

# scripted stub model: one canned tool call per assistant turn so far, then stop
SCRIPT = [
    {"name": "TodoWrite", "args": {"todos": [
        {"step": "read config", "status": "completed"},
        {"step": "fix typo", "status": "in_progress"}]}},
    {"name": "EditFile", "args": {"path": "config.toml", "old": "nmae", "new": "name"}},  # denied: plan mode
    {"name": "ExitPlanMode", "args": {}},
    {"name": "EditFile", "args": {"path": "config.toml", "old": "nmae", "new": "name"}},  # now allowed
    {"name": "Bash", "args": {"command": "rm -rf /"}},                                    # blocked by hook
]


def model(messages, registry, session):
    turns = sum(1 for m in messages if m["role"] == "assistant")
    if turns < len(SCRIPT):
        return {"stop_reason": "tool_use", "text": "", "tool_calls": [SCRIPT[turns]]}

    return {"stop_reason": "end_turn", "text": "done", "tool_calls": []}


def demo():
    session = Session(mode=PLAN)
    files = {"config.toml": "nmae = 'x'"}   # the typo we will fix

    reg = Registry()
    reg.register(todo_tool(session))
    reg.register(exit_plan_mode_tool(session, to_mode=ACCEPT_EDITS))

    def edit(a):
        files[a["path"]] = files[a["path"]].replace(a["old"], a["new"])
        return f"edited {a['path']}"
    reg.register(Tool("EditFile", edit, is_edit=True))
    reg.register(Tool("Bash", lambda a: f"ran {a['command']}"))

    hooks = Hooks()
    log = []
    hooks.on(PRE_TOOL_USE, lambda n, a: {"deny": True, "message": "refusing rm -rf"}
             if n == "Bash" and "rm -rf" in a.get("command", "") else None)
    hooks.on(POST_TOOL_USE, lambda n, a, r: log.append(n))
    approver = lambda name, args: name == "ExitPlanMode"   # the human approves the plan, nothing else

    out = run("fix the typo in config.toml", model, reg, session, hooks=hooks, approver=approver)

    assert out == "done"
    assert files["config.toml"] == "name = 'x'", files                 # the edit landed
    assert session.mode == ACCEPT_EDITS                                # plan was approved
    assert session.todos[0]["step"] == "read config"                   # todos recorded
    assert log == ["TodoWrite", "ExitPlanMode", "EditFile"], log       # only executed tools reach PostToolUse

    print("05 planning: ok ->", files["config.toml"], log)


if __name__ == "__main__":
    demo()
