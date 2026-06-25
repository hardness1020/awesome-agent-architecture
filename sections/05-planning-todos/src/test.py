"""Section 5 offline checks: the plan-mode arc through the loop's dispatch. No key, no network.

    python sections/05-planning-todos/src/test.py
"""
from types import SimpleNamespace

from hooks import Hooks
from loop import Session, _dispatch
from permissions import ACCEPT_EDITS, PLAN
from planning import exit_plan_mode_tool, todo_tool
from tools import Registry, Tool


def _blk(name, tool_input):
    return SimpleNamespace(type="tool_use", id=name, name=name, input=tool_input)


def test():
    session = Session(mode=PLAN)
    files = {"config.toml": "nmae = 'x'"}

    reg = Registry()
    reg.register(todo_tool(session))
    reg.register(exit_plan_mode_tool(session, to_mode=ACCEPT_EDITS))

    def edit(a):
        files[a["path"]] = files[a["path"]].replace(a["old"], a["new"])
        return f"edited {a['path']}"
    reg.register(Tool("EditFile", edit, description="Edit a file in place.", is_edit=True))

    approve_plan = lambda name, args: name == "ExitPlanMode"   # the human approves only the plan
    dispatch = lambda b: _dispatch(b, reg, session, Hooks(), approve_plan)

    dispatch(_blk("TodoWrite", {"todos": [{"step": "fix typo", "status": "in_progress"}]}))
    assert session.todos[0]["step"] == "fix typo"              # todos recorded (read-only, allowed)

    denied = dispatch(_blk("EditFile", {"path": "config.toml", "old": "nmae", "new": "name"}))
    assert "not allowed in plan mode" in denied["content"]     # edits denied while planning

    dispatch(_blk("ExitPlanMode", {}))
    assert session.mode == ACCEPT_EDITS                        # plan approved -> mode flipped

    dispatch(_blk("EditFile", {"path": "config.toml", "old": "nmae", "new": "name"}))
    assert files["config.toml"] == "name = 'x'", files         # now the edit lands

    print("05 planning: ok")


if __name__ == "__main__":
    test()
