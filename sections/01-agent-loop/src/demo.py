"""Section 1 self-check. The model is a stub, so this runs with no API key.

    python sections/01-agent-loop/src/demo.py
"""
from loop import run


def stub_model(messages):
    """Turn 1 -> ask for a tool; turn 2 -> answer from the result."""
    ran = any(m.get("role") == "tool" for m in messages)
    if not ran:
        return {"stop_reason": "tool_use", "text": "checking",
                "tool_calls": [{"name": "get_time", "args": {}}]}

    last = next(m["content"] for m in reversed(messages) if m.get("role") == "tool")
    return {"stop_reason": "end_turn", "tool_calls": [], "text": f"The time is {last}."}


def demo():
    assert run("what time is it?", stub_model) == "The time is 2026-06-24T10:00:00Z."
    print("01 agent_loop: ok")


if __name__ == "__main__":
    demo()
