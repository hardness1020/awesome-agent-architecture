"""Agent loop (sections 1 to 8). Changed from section 5: one call to
context.manage() runs at the top of every iteration, before the model call.

That single line keeps messages[] under the window: cheap, near-lossless passes
each turn, and an LLM summary only when a token estimate is exceeded (see
context.py). A `summarizer` is threaded through so the loop can collapse its own
history when needed. Everything else is the section-5 loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import context
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
        hooks: Hooks | None = None, approver=None, summarizer=None, max_steps=20):
    hooks = hooks or Hooks()
    approver = approver or (lambda name, args: False)
    messages = [{"role": "user", "content": user_intent}]

    for _ in range(max_steps):
        messages = context.manage(messages, summarizer=summarizer)   # 8 · keep context under the window
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
