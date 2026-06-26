"""Agent loop with planning / plan mode (section 5), the full pipeline.

Changed from 04: the mutable bits (mode, allow_rules, todos) move onto a
Session so plan-mode tools can flip the mode mid-run. The gate reads
`session.mode` live, so approving a plan changes what the next call may do.
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


def run_turn(messages, model, registry: Registry, session: Session,
        hooks: Hooks | None = None, approver=None, max_steps=20):
    hooks = hooks or Hooks()
    approver = approver or (lambda name, args: False)
    
    for _ in range(max_steps):
        response = model(messages, registry)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return final_text(response)

        results = [_dispatch(b, registry, session, hooks, approver)
                   for b in response.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})

    raise RuntimeError("hit max_steps without end_turn")


def _dispatch(block, registry, session, hooks, approver):
    name, args = block.name, block.input
    tool = registry.get(name)
    res = lambda content: {"type": "tool_result", "tool_use_id": block.id, "content": content}
    if tool is None:
        return res(f"error: no tool {name!r}")

    blocked, args, msg = hooks.fire_pre(name, args)                         # 4 · PreToolUse
    if blocked:
        return res(msg)

    decision = permissions.decide(tool, session.mode, session.allow_rules)  # 3 · gate (live mode)
    if decision == "deny":
        return res(f"{name} not allowed in {session.mode} mode")
    if decision == "ask" and not approver(name, args):
        return res(f"{name} denied by user")

    out = res(run_tool(tool, args))
    hooks.fire_post(name, args, out)                                        # 4 · PostToolUse
    return out


def final_text(response):
    """The model's last words: concatenate its text blocks."""
    return "".join(b.text for b in response.content if b.type == "text")
