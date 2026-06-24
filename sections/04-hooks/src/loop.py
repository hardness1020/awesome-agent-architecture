"""Agent loop with hooks (section 4).

Changed from 03: `_dispatch` fires PreToolUse before the gate (a hook can block
or rewrite the call) and PostToolUse after execution, and `run()` carries a
Hooks instance. Section 5 moves the mutable state onto a Session.
"""
from __future__ import annotations

import permissions
from hooks import Hooks
from tools import Registry, run_tool


def run(user_intent, model, registry: Registry, hooks: Hooks | None = None,
        mode=permissions.DEFAULT, allow_rules=None, approver=None, max_steps=10):
    hooks = hooks or Hooks()
    allow_rules = allow_rules or set()
    approver = approver or (lambda name, args: False)
    messages = [{"role": "user", "content": user_intent}]

    for _ in range(max_steps):
        reply = model(messages, registry)
        messages.append({"role": "assistant", **reply})

        if reply["stop_reason"] == "end_turn":
            return reply["text"]

        for call in reply["tool_calls"]:
            messages.append(_dispatch(call, registry, hooks, mode, allow_rules, approver))

    raise RuntimeError("hit max_steps without end_turn")


def _dispatch(call, registry, hooks, mode, allow_rules, approver):
    name, args = call["name"], call.get("args", {})
    tool = registry.get(name)
    res = lambda status, content: {"role": "tool", "name": name, "status": status, "content": content}
    if tool is None:
        return res("error", f"no tool {name!r}")

    blocked, args, msg = hooks.fire_pre(name, args)          # 4 · PreToolUse: rewrite or block
    if blocked:
        return res("blocked", msg)

    decision = permissions.decide(tool, mode, allow_rules)   # 3 · the gate
    if decision == "deny":
        return res("denied", f"{name} not allowed in {mode} mode")
    if decision == "ask" and not approver(name, args):
        return res("denied", f"{name} denied by user")

    out = {"role": "tool", "name": name, **run_tool(tool, args)}
    hooks.fire_post(name, args, out)                         # 4 · PostToolUse: observe
    return out
