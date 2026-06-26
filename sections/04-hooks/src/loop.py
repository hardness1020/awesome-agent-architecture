"""Agent loop with hooks (section 4).

Changed from 03: `_dispatch` fires PreToolUse before the gate (a hook can block
or rewrite the call) and PostToolUse after execution, and `run()` carries a
Hooks instance. Section 5 moves the mutable state onto a Session.
"""
from __future__ import annotations

import permissions
from hooks import Hooks
from tools import Registry, run_tool


def run_turn(messages, model, registry: Registry, hooks: Hooks | None = None,
        mode=permissions.DEFAULT, allow_rules=None, approver=None, max_steps=10):
    hooks = hooks or Hooks()
    allow_rules = allow_rules or set()
    approver = approver or (lambda name, args: False)
    
    for _ in range(max_steps):
        response = model(messages, registry)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return final_text(response)

        results = [_dispatch(b, registry, hooks, mode, allow_rules, approver)
                   for b in response.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})

    raise RuntimeError("hit max_steps without end_turn")


def _dispatch(block, registry, hooks, mode, allow_rules, approver):
    name, args = block.name, block.input
    tool = registry.get(name)
    res = lambda content: {"type": "tool_result", "tool_use_id": block.id, "content": content}
    if tool is None:
        return res(f"error: no tool {name!r}")

    blocked, args, msg = hooks.fire_pre(name, args)          # 4 · PreToolUse: rewrite or block
    if blocked:
        return res(msg)

    decision = permissions.decide(tool, mode, allow_rules)   # 3 · the gate
    if decision == "deny":
        return res(f"{name} not allowed in {mode} mode")
    if decision == "ask" and not approver(name, args):
        return res(f"{name} denied by user")

    out = res(run_tool(tool, args))
    hooks.fire_post(name, args, out)                         # 4 · PostToolUse: observe
    return out


def final_text(response):
    """The model's last words: concatenate its text blocks."""
    return "".join(b.text for b in response.content if b.type == "text")
