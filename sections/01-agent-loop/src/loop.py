"""Agent loop (section 1): the core while-loop, and the conversation around it.

Two nested loops. The inner loop is one user turn: call the model, and while it
asks for a tool, run the tool, feed the result back as a `tool_result`, and call
again; stop when it does not. The outer loop is the conversation: the SAME
`messages[]` persists, and each new user turn is appended to it, so the model
sees every prior message exactly on the next call. `run_turn` is the inner loop;
the caller owns `messages` and drives the outer one (see demo.py).

The loop speaks the Anthropic Messages format directly (content blocks,
`tool_use`, `tool_result`), so `model` is just a thin call to
client.messages.create. Swap that one function and run_turn is unchanged.
Sections 2 to 11 carry this file forward and evolve it.
"""
from datetime import datetime, timezone


def get_time(_input):
    """A trivial read-only tool: the model cannot know the time, so it must ask."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


TOOL_SCHEMAS = [{                                # advertised to the model (Anthropic format)
    "name": "get_time",
    "description": "Return the current UTC time as an ISO 8601 string.",
    "input_schema": {"type": "object", "properties": {}},
}]

HANDLERS = {"get_time": get_time}               # section 2 replaces this with a Registry


def run_tool(name, tool_input):
    """Dispatch one tool call to its handler; any failure comes back as text."""
    fn = HANDLERS.get(name)
    if fn is None:
        return f"error: no tool {name!r}"
    try:
        return fn(tool_input)
    except Exception as e:  # ponytail: failure is a result fed back, never a crashed loop
        return f"error: {e}"


def run_turn(messages, model, max_steps=10):
    """Run one user turn to completion over the shared conversation `messages`.

    Precondition: the new user message is already the last item in `messages`.
    The model and tools iterate, each step appended to the SAME list, until the
    model stops asking for tools. Returns the assistant's final text; `messages`
    is mutated in place, so the next turn sees this whole exchange verbatim.
    """
    for _ in range(max_steps):                  # ponytail: max_steps is the no-infinite-loop backstop
        response = model(messages)              # one model call -> an Anthropic Message
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":  # model produced its final answer for this turn
            return final_text(response)

        results = []                            # tool_use: run each call, feed results back
        for block in response.content:
            if block.type == "tool_use":
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": run_tool(block.name, block.input),
                })
        messages.append({"role": "user", "content": results})

    raise RuntimeError("hit max_steps without end_turn")  # the no-stop-condition failure mode


def final_text(response):
    """The model's last words: concatenate its text blocks."""
    return "".join(b.text for b in response.content if b.type == "text")
