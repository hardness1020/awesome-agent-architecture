"""Section 21 offline checks, no key, no network.

test_pass_first_try(): a passing candidate returns after one attempt.

test_feedback_retry(): a failed verdict rides into the retry as feedback, and
attempt two passes because it saw why attempt one failed.

test_budget_escalate(): a worker that never passes stops at the budget with
ok=False. The ceiling is the harness's range(), not the model's judgment.

test_agent_checker(): the checker runs the inner loop on a fresh messages[]
and parses the first-word PASS/FAIL verdict contract.

    python sections/21-loop-engineering/src/test.py
"""
from verify import agent_checker, verified_run


def test_pass_first_try():
    checker = lambda task, out: {"passed": out == "42", "reason": "must be 42"}
    r = verified_run("add 27 and 15", lambda p: "42", checker, budget=3)
    assert r["ok"] and r["output"] == "42" and len(r["attempts"]) == 1

    print("21 loop-eng: pass-first-try ok")


def test_feedback_retry():
    prompts = []

    def worker(prompt):
        prompts.append(prompt)
        return "42" if "prior attempt" in prompt.lower() else "41"   # attempt two reads the feedback

    checker = lambda task, out: {"passed": out == "42", "reason": "off by one"}
    r = verified_run("add 27 and 15", worker, checker, budget=3)
    assert r["ok"] and len(r["attempts"]) == 2
    assert r["attempts"][0]["passed"] is False
    assert "prior" not in prompts[0].lower()       # attempt one saw only the task
    assert "off by one" in prompts[1]              # the verdict reached attempt two as data

    print("21 loop-eng: feedback-retry ok")


def test_budget_escalate():
    calls = []
    worker = lambda p: (calls.append(p), "wrong")[1]
    checker = lambda task, out: {"passed": False, "reason": "still wrong"}
    r = verified_run("impossible", worker, checker, budget=2)
    assert r["ok"] is False and r["output"] is None
    assert len(calls) == 2 and len(r["attempts"]) == 2   # stopped at the ceiling, no attempt 3

    print("21 loop-eng: budget-escalate ok")


class _Text:                                       # a stand-in Anthropic text block
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:                                        # a stand-in Anthropic Message
    def __init__(self, text):
        self.content = [_Text(text)]
        self.stop_reason = "end_turn"


def test_agent_checker():
    seen = []

    def model(messages, registry, system):
        seen.append(list(messages))
        return _Msg("FAIL the output is prose, not a number")

    check = agent_checker("output is exactly one number", model)
    v = check("add 27 and 15", "the answer is forty-two")
    assert v["passed"] is False and "prose" in v["reason"]
    assert len(seen[0]) == 1                       # a fresh messages[] per grade (section 6)

    passing = agent_checker("output is exactly one number",
                            lambda m, r, s: _Msg("PASS exactly one number"))
    assert passing("add 27 and 15", "42")["passed"] is True

    print("21 loop-eng: agent-checker ok")


if __name__ == "__main__":
    test_pass_first_try()
    test_feedback_retry()
    test_budget_escalate()
    test_agent_checker()
