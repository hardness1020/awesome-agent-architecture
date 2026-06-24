"""Agent loop (section 1): the core while-loop. Branch on stop_reason, run
the requested tool, append the result, loop. Sections 2 to 5 carry this same
file forward and evolve it. Run it via demo.py (no API key needed).
"""


def get_time(_args):
    return "2026-06-24T10:00:00Z"


TOOLS = {"get_time": get_time}   # section 2 replaces this dict with a Registry


def run_tool(call):
    name = call["name"]
    fn = TOOLS.get(name)
    if fn is None:
        return {"role": "tool", "name": name, "content": f"error: no tool {name!r}"}

    try:
        return {"role": "tool", "name": name, "content": fn(call.get("args", {}))}
    except Exception as e:  # ponytail: failure comes back as a result, never crashes the loop
        return {"role": "tool", "name": name, "content": f"error: {e}"}


def run(user_intent, model, max_steps=10):
    messages = [{"role": "user", "content": user_intent}]

    for _ in range(max_steps):                  # ponytail: max_steps is the no-infinite-loop backstop
        reply = model(messages)
        messages.append({"role": "assistant", **reply})

        if reply["stop_reason"] == "end_turn":
            return reply["text"]

        for call in reply["tool_calls"]:         # tool_use: run each, feed results back
            messages.append(run_tool(call))

    raise RuntimeError("hit max_steps without end_turn")  # the no-stop-condition failure mode
