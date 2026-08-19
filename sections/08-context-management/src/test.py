"""Section 8 offline checks: the three reduction passes, plus the spill contrast. No key, no network.

    python sections/08-context-management/src/test.py
"""
from pathlib import Path

import context
import spill


def _tool_result(s):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": s}]}


def test():
    # budget: an oversized tool result is persisted to a preview
    msgs = [_tool_result("X" * 1000)]
    context._budget(msgs)
    assert msgs[0]["content"][0]["content"].endswith("<persisted-output>")

    # micro: old tool-result bodies become a stub; the recent tail is kept verbatim
    msgs = [_tool_result("old body") for _ in range(6)]
    context._micro(msgs, keep_recent=2)
    assert all(m["content"][0]["content"] == "<elided>" for m in msgs[:4])
    assert msgs[-1]["content"][0]["content"] == "old body"

    # auto: fires only when still over the token limit, and collapses the middle
    big = [{"role": "assistant", "content": "reasoning " * 60} for _ in range(12)]
    msgs = [{"role": "user", "content": "do the thing"}] + big
    out = context.manage(msgs, summarizer=lambda ms: "did 12 steps")
    assert any(isinstance(m["content"], str) and "summary of" in m["content"] for m in out)
    assert len(out) < len(big) + 1

    # spill: the full result lands on disk, and the preview says where to read it
    full = "A" * 500 + "B" * 500
    msgs = [_tool_result(full)]
    spill.spill_results(msgs, spill.SpillStore())
    kept = msgs[0]["content"][0]["content"]
    assert len(kept) < len(full) and "chars spilled" in kept
    assert kept.startswith("A" * 20) and "B" * 20 in kept   # a head and a tail stay readable
    path = kept.split('path="')[1].split('"')[0]
    assert Path(path).read_text() == full            # nothing was lost, unlike _budget

    # spill: a small result is left alone
    msgs = [_tool_result("short")]
    spill.spill_results(msgs, spill.SpillStore())
    assert msgs[0]["content"][0]["content"] == "short"

    # spill: an SDK block object in the content list is skipped, not crashed on
    msgs = [{"role": "user", "content": ["an SDK text block"]}]
    spill.spill_results(msgs, spill.SpillStore())

    print("08 context: ok")


if __name__ == "__main__":
    test()
