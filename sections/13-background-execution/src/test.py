"""Section 13 offline checks: off-loop start, the notification queue, the
turn-start drain, and backgrounding any tool (up to a whole agent). No key, no
network.

    python sections/13-background-execution/src/test.py
"""
import threading
import time

from background import Runtime, backgroundable, drain_into
from tools import Tool


def _wait(rt, tid):
    for _ in range(200):                                   # spin briefly for the worker thread
        if rt.state(tid) != "running":
            return
        time.sleep(0.01)
    raise AssertionError("background task never finished")


def test():
    rt = Runtime()

    # start returns a handle without blocking: a gated task is still running
    gate = threading.Event()
    tid = rt.start(lambda: (gate.wait(), "build output")[1])
    assert tid == 1 and rt.state(tid) == "running"
    assert rt.drain() == []                                # nothing has completed yet

    # let it finish: exactly one completion notification, then the queue is empty
    gate.set()
    _wait(rt, tid)
    notes = rt.drain()
    assert len(notes) == 1 and "task 1 completed" in notes[0] and "build output" in notes[0]
    assert rt.drain() == []

    # a failed background task still reports back (it doesn't crash the loop)
    fid = rt.start(lambda: 1 / 0)
    _wait(rt, fid)
    assert "task 2 failed" in rt.drain()[0]

    # backgroundable wraps ANY tool. Here the "tool" stands in for a whole agent
    # (section 6): one call runs a full sub-loop off the main loop.
    agent_runs = []

    def fake_agent(a):                                     # pretend this spawns and runs a child loop
        agent_runs.append(a["description"])
        return f"agent answered: {a['description']}"

    agent = backgroundable(Tool("Agent", fake_agent, is_read_only=True), rt)
    assert "run_in_background" in agent.input_schema["properties"]
    assert agent.is_read_only                              # replace() kept the original's flags

    # no flag: the whole agent runs inline and returns its real answer
    assert agent.run({"description": "summarize the repo"}) == "agent answered: summarize the repo"

    # with the flag: the whole agent goes off-loop, handle returns now, answer arrives later
    handle = agent.run({"description": "audit the codebase", "run_in_background": True})
    assert "started background task" in handle and "Agent" in handle
    _wait(rt, 3)
    note = rt.drain()[0]
    assert "audit the codebase" in note and "completed" in note
    assert agent_runs == ["summarize the repo", "audit the codebase"]

    # drain_into folds a pending completion into the next user turn
    rt._finish(9, "completed", "DEPLOYED")                 # pre-load a note as if a task just finished
    messages = [{"role": "user", "content": "did the deploy finish?"}]
    drain_into(messages, rt)
    assert messages[-1]["content"].startswith("<task_notification>")
    assert "DEPLOYED" in messages[-1]["content"] and "did the deploy finish?" in messages[-1]["content"]

    # no runtime, or nothing pending: the message is untouched
    msg = [{"role": "user", "content": "hello"}]
    drain_into(msg, None)
    drain_into(msg, rt)
    assert msg[-1]["content"] == "hello"

    print("13 background: ok")


if __name__ == "__main__":
    test()
