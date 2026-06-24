"""Agent loop (section 1), now using the tool runtime (section 2).

Changed from 01: the inline TOOLS dict became a Registry, and tool execution
goes through `_dispatch`. `run()` takes a `registry`; the model sees it too.
Sections 3 and 4 add a permission gate and hooks inside `_dispatch`.
"""
from __future__ import annotations

from tools import Registry, run_tool


def run(user_intent, model, registry: Registry, max_steps=10):
    messages = [{"role": "user", "content": user_intent}]

    for _ in range(max_steps):                  # ponytail: max_steps is the no-infinite-loop backstop
        reply = model(messages, registry)
        messages.append({"role": "assistant", **reply})

        if reply["stop_reason"] == "end_turn":
            return reply["text"]

        for call in reply["tool_calls"]:
            messages.append(_dispatch(call, registry))

    raise RuntimeError("hit max_steps without end_turn")


def _dispatch(call, registry):
    """Resolve and run one tool call. Sections 3 and 4 grow this function."""
    name, args = call["name"], call.get("args", {})
    tool = registry.get(name)
    if tool is None:
        return {"role": "tool", "name": name, "status": "error", "content": f"no tool {name!r}"}

    return {"role": "tool", "name": name, **run_tool(tool, args)}
