"""Section 2 self-check: the loop dispatching through a registry, plus the
concurrency-safe parallel primitive. Stubbed model, no API key.

    python sections/02-tool-runtime/src/demo.py
"""
from loop import run
from tools import Registry, Tool, run_concurrently


def stub_model(messages, registry):
    """Turn 1 -> read two files; turn 2 -> combine the results."""
    ran = [m for m in messages if m.get("role") == "tool"]
    if not ran:
        return {"stop_reason": "tool_use", "text": "reading",
                "tool_calls": [{"name": "ReadFile", "args": {"path": "a.txt"}},
                               {"name": "ReadFile", "args": {"path": "b.txt"}}]}

    return {"stop_reason": "end_turn", "tool_calls": [],
            "text": " + ".join(m["content"] for m in ran)}


def demo():
    files = {"a.txt": "alpha", "b.txt": "beta"}
    reg = Registry()
    reg.register(Tool("ReadFile", lambda a: files[a["path"]], is_read_only=True, is_concurrency_safe=True))

    # the loop dispatches the two reads and the model combines them
    assert run("read both files", stub_model, reg) == "alpha + beta"

    # run_concurrently is the batching primitive for concurrency-safe calls
    results = run_concurrently(reg, [{"name": "ReadFile", "args": {"path": "a.txt"}},
                                     {"name": "ReadFile", "args": {"path": "b.txt"}}])
    assert [r["content"] for r in results] == ["alpha", "beta"]

    print("02 tool_runtime: ok")


if __name__ == "__main__":
    demo()
