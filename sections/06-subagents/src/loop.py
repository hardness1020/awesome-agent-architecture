"""Agent loop (sections 1 to 6). Unchanged from section 5.

A subagent (subagents.py) is this same `run()` invoked again with a fresh
messages[] inside a tool call, so section 6 adds a tool, not loop code. The
loop body stays the four numbered steps; delegation rides on top of them.
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
