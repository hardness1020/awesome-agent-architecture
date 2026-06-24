"""Agent loop with the permission gate (section 3).

Changed from 02: `_dispatch` now calls `permissions.decide` before running a
tool, and `run()` carries the permission `mode`, `allow_rules`, and an
`approver` for the 'ask' path. Section 4 adds hooks around this same path.
"""
from __future__ import annotations

import permissions
from tools import Registry, run_tool


def run(user_intent, model, registry: Registry, mode=permissions.DEFAULT,
        allow_rules=None, approver=None, max_steps=10):
    allow_rules = allow_rules or set()
    approver = approver or (lambda name, args: False)   # no human present: 'ask' means 'no'
    messages = [{"role": "user", "content": user_intent}]

    for _ in range(max_steps):
        reply = model(messages, registry)
        messages.append({"role": "assistant", **reply})

        if reply["stop_reason"] == "end_turn":
            return reply["text"]

        for call in reply["tool_calls"]:
            messages.append(_dispatch(call, registry, mode, allow_rules, approver))

    raise RuntimeError("hit max_steps without end_turn")


def _dispatch(call, registry, mode, allow_rules, approver):
    name, args = call["name"], call.get("args", {})
    tool = registry.get(name)
    res = lambda status, content: {"role": "tool", "name": name, "status": status, "content": content}
    if tool is None:
        return res("error", f"no tool {name!r}")

    decision = permissions.decide(tool, mode, allow_rules)   # 3 · the gate
    if decision == "deny":
        return res("denied", f"{name} not allowed in {mode} mode")
    if decision == "ask" and not approver(name, args):
        return res("denied", f"{name} denied by user")

    return {"role": "tool", "name": name, **run_tool(tool, args)}
