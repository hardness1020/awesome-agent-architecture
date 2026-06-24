"""Agent loop with planning / plan mode (section 5), the full pipeline.

Changed from 04: the mutable bits (mode, allow_rules, todos) move onto a
Session so plan-mode tools can flip the mode mid-run, and `model()` receives the
session. The gate now reads `session.mode` live, so approving a plan changes
what the very next call is allowed to do.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import permissions
from hooks import Hooks
from tools import Registry, run_tool


@dataclass
class Session:
    """Mutable harness state that outlives a turn."""
    mode: str = permissions.DEFAULT
    allow_rules: set = field(default_factory=set)
    todos: list = field(default_factory=list)


def run(user_intent, model, registry: Registry, session: Session,
        hooks: Hooks | None = None, approver=None, max_steps=20):
    hooks = hooks or Hooks()
    approver = approver or (lambda name, args: False)
    messages = [{"role": "user", "content": user_intent}]

    for _ in range(max_steps):
        reply = model(messages, registry, session)
        messages.append({"role": "assistant", **reply})

        if reply["stop_reason"] == "end_turn":
            return reply["text"]

        for call in reply["tool_calls"]:
            messages.append(_dispatch(call, registry, session, hooks, approver))

    raise RuntimeError("hit max_steps without end_turn")


def _dispatch(call, registry, session, hooks, approver):
    name, args = call["name"], call.get("args", {})
    tool = registry.get(name)
    res = lambda status, content: {"role": "tool", "name": name, "status": status, "content": content}
    if tool is None:
        return res("error", f"no tool {name!r}")

    blocked, args, msg = hooks.fire_pre(name, args)                         # 4 · PreToolUse
    if blocked:
        return res("blocked", msg)

    decision = permissions.decide(tool, session.mode, session.allow_rules)  # 3 · gate (live mode)
    if decision == "deny":
        return res("denied", f"{name} not allowed in {session.mode} mode")
    if decision == "ask" and not approver(name, args):
        return res("denied", f"{name} denied by user")

    out = {"role": "tool", "name": name, **run_tool(tool, args)}
    hooks.fire_post(name, args, out)                                        # 4 · PostToolUse
    return out
