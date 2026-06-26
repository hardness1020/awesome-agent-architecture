"""Agent loop (sections 1 to 9). Changed from section 8: memory (section 9) is
recalled into the opening turn and extracted at run end.

Before the loop, a Store ranks the durable memory files against the user's
intent and injects the few relevant bodies as a <system-reminder> (read-only).
When the run ends with no tool call, the Store extracts new memories from the
transcript (write-only). messages[] still dies with the run; the Store is what
outlives it. Everything else is the section-8 loop.
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


def run_turn(messages, model, registry: Registry, session: Session,
        hooks: Hooks | None = None, approver=None, summarizer=None, memory=None, max_steps=20):
    hooks = hooks or Hooks()
    approver = approver or (lambda name, args: False)

    if memory is not None:
        user_text = messages[-1]["content"]                # the new user turn (already appended)
        recalled = memory.recall(user_text)                # 9 · inject relevant memories (read-only)
        if recalled:
            messages[-1]["content"] = f"<system-reminder>\n{recalled}\n</system-reminder>\n\n{user_text}"

    for _ in range(max_steps):
        messages = context.manage(messages, summarizer=summarizer)   # 8 · keep context under the window
        response = model(messages, registry)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            if memory is not None:
                memory.write(messages)                     # 9 · extract new memories at run end (write-only)
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
