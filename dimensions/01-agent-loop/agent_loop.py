"""Subsystem 1: the agent loop, stripped to its essence.

Runs with no API key. `stub_model` fakes two turns: first it asks for a tool,
then it answers. That is enough to show the only thing that matters here:
branch on stop_reason, append the result, loop.

Swap `stub_model` for a real client (Anthropic, OpenAI, ...) and this is a
real agent. The loop body does not change.

    python agent_loop.py
"""


# --- tools: a dispatch map from name to a plain function -------------------

def get_time(_args):
    return "2026-06-24T10:00:00Z"


TOOLS = {"get_time": get_time}


def run_tool(call):
    fn = TOOLS.get(call["name"])
    if fn is None:
        content = f"error: no tool {call['name']!r}"
    else:
        try:
            content = fn(call.get("args", {}))
        except Exception as e:  # ponytail: failure comes back as a result, never crashes the loop
            content = f"error: {e}"
    return {"role": "tool", "name": call["name"], "content": content}


# --- the stub model: fakes the two stop_reasons a real API returns ---------

def stub_model(messages):
    """Pretend to be an LLM. Turn 1 -> tool_use, turn 2 -> end_turn."""
    already_ran_tool = any(m.get("role") == "tool" for m in messages)
    if not already_ran_tool:
        return {"stop_reason": "tool_use",
                "tool_calls": [{"name": "get_time", "args": {}}],
                "text": "let me check the time"}
    last_result = next(m["content"] for m in reversed(messages) if m.get("role") == "tool")
    return {"stop_reason": "end_turn", "tool_calls": [], "text": f"The time is {last_result}."}


# --- the loop: the whole agent ---------------------------------------------

def run(user_intent, model=stub_model, max_steps=10):
    messages = [{"role": "user", "content": user_intent}]
    for _ in range(max_steps):                  # ponytail: max_steps is the no-infinite-loop backstop
        reply = model(messages)
        messages.append({"role": "assistant", **reply})
        if reply["stop_reason"] == "tool_use":
            for call in reply["tool_calls"]:
                messages.append(run_tool(call))  # feed every outcome back into messages[]
            continue
        if reply["stop_reason"] == "end_turn":
            return reply["text"]
    raise RuntimeError("hit max_steps without end_turn")  # the no-stop-condition failure mode


def demo():
    answer = run("what time is it?")
    assert answer == "The time is 2026-06-24T10:00:00Z.", answer
    print(answer)


if __name__ == "__main__":
    demo()
