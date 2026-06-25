"""Section 2 offline checks: registry dispatch and the parallel primitive. No key, no network.

    python sections/02-tool-runtime/src/test.py
"""
from types import SimpleNamespace

from loop import _dispatch
from tools import Registry, Tool, run_concurrently

FILES = {"a.txt": "alpha", "b.txt": "beta"}


def read_file_tool():
    return Tool("ReadFile", lambda a: FILES[a["path"]],
                description="Read a file's contents by path.",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}},
                              "required": ["path"]},
                is_read_only=True, is_concurrency_safe=True)


def test():
    reg = Registry()
    reg.register(read_file_tool())

    block = SimpleNamespace(type="tool_use", id="t1", name="ReadFile", input={"path": "a.txt"})
    assert _dispatch(block, reg) == {"type": "tool_result", "tool_use_id": "t1", "content": "alpha"}

    miss = _dispatch(SimpleNamespace(type="tool_use", id="t2", name="Nope", input={}), reg)
    assert miss["content"].startswith("error: no tool")

    results = run_concurrently(reg, [{"name": "ReadFile", "input": {"path": "a.txt"}},
                                     {"name": "ReadFile", "input": {"path": "b.txt"}}])
    assert results == ["alpha", "beta"], results       # safe reads batch, order preserved

    print("02 tool_runtime: ok")


if __name__ == "__main__":
    test()
