"""Section 1 offline checks: tool dispatch and final-text extraction. No key, no network.

    python sections/01-agent-loop/src/test.py
"""
from loop import final_text, run_tool


def test():
    assert run_tool("get_time", {}).startswith("20")     # real ISO timestamp
    assert run_tool("nope", {}).startswith("error")      # unknown tool -> error result

    class _Block:                                         # a stand-in Anthropic text block
        type, text = "text", "hi"
    assert final_text(type("R", (), {"content": [_Block()]})) == "hi"

    print("01 agent_loop: ok")


if __name__ == "__main__":
    test()
