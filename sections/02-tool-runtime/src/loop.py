"""Agent loop (section 2): dispatch through a tool Registry.

Changed from 01: the inline tools move into a Registry (tools.py), and each
tool_use block routes through `_dispatch`. `run()` takes a `registry`, and the
model is handed it too so it can advertise the tool schemas. The loop body is
otherwise the section-1 while-loop in Anthropic Messages format. Sections 3 and
4 grow `_dispatch` with a permission gate and hooks.
"""
from __future__ import annotations

from tools import Registry, run_tool


def run_turn(messages, model, registry: Registry, max_steps=10):
    for _ in range(max_steps):                  # ponytail: max_steps is the no-infinite-loop backstop
        response = model(messages, registry)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return final_text(response)

        results = [_dispatch(b, registry) for b in response.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})

    raise RuntimeError("hit max_steps without end_turn")


def _dispatch(block, registry):
    """Resolve a tool_use block, run it, wrap the output as a tool_result.
    Sections 3 and 4 grow this function."""
    tool = registry.get(block.name)
    content = f"error: no tool {block.name!r}" if tool is None else run_tool(tool, block.input)
    return {"type": "tool_result", "tool_use_id": block.id, "content": content}


def final_text(response):
    """The model's last words: concatenate its text blocks."""
    return "".join(b.text for b in response.content if b.type == "text")
