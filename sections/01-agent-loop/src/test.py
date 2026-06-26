"""Section 1 offline checks: tool dispatch, final-text, and multi-turn memory.
No key, no network.

    python sections/01-agent-loop/src/test.py
"""
from loop import final_text, run_tool, run_turn


class _Text:                                             # a stand-in Anthropic text block
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:                                              # a stand-in Anthropic Message
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


def test():
    assert run_tool("get_time", {}).startswith("20")     # real ISO timestamp
    assert run_tool("nope", {}).startswith("error")      # unknown tool -> error result
    assert final_text(_Msg([_Text("hi")])) == "hi"

    # multi-turn: one persistent messages[] grows, and turn 2 sees turn 1 verbatim
    seen = {}

    def model(messages):
        seen["count"] = len(messages)                    # how many prior messages this turn sees
        return _Msg([_Text(f"reply {len(messages)}")])

    messages = []
    messages.append({"role": "user", "content": "first"})
    assert run_turn(messages, model) == "reply 1"        # saw only the new user message
    assert len(messages) == 2                            # user + assistant appended in place

    messages.append({"role": "user", "content": "second"})
    run_turn(messages, model)
    assert seen["count"] == 3                            # turn 2 saw user + assistant + user
    assert messages[0]["content"] == "first"            # turn 1 still present, exactly

    print("01 agent_loop: ok")


if __name__ == "__main__":
    test()
