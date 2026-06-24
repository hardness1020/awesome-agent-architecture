"""Tool runtime (section 2): the Tool contract, a registry, dispatch, and
parallel execution of concurrency-safe calls. Introduced in section 2 and
carried unchanged into sections 3 to 5.

Mirrors Claude Code's Tool.ts (name, isReadOnly, isConcurrencySafe) and the
partition-then-run step in services/tools/.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    run: Callable[[dict], Any]
    is_read_only: bool = False
    is_concurrency_safe: bool = False   # may share a parallel batch
    is_edit: bool = False               # a file edit; read by the permission gate (section 3)


class Registry:
    """Name to Tool. Adding a tool is registering one handler."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)


def run_tool(tool: Tool, args: dict) -> dict:
    """Execute one tool, turning any failure into a result (never raises)."""
    try:
        return {"status": "ok", "content": tool.run(args)}
    except Exception as e:  # ponytail: failure is a result fed back, not a crashed loop
        return {"status": "error", "content": f"{type(e).__name__}: {e}"}


def run_concurrently(registry: Registry, calls: list[dict]) -> list[dict]:
    """Dispatch a turn's tool calls; concurrency-safe ones share one parallel
    batch. Output order matches input. The loop dispatches sequentially for
    readability; this is the batching primitive the real runtime applies."""
    tools = [registry.get(c["name"]) for c in calls]
    out: dict[int, dict] = {}

    safe = [i for i, t in enumerate(tools) if t and t.is_concurrency_safe]
    if safe:
        with ThreadPoolExecutor(max_workers=len(safe)) as pool:
            for i, res in zip(safe, pool.map(lambda i: run_tool(tools[i], calls[i].get("args", {})), safe)):
                out[i] = res

    for i, t in enumerate(tools):
        if i not in out:
            out[i] = {"status": "error", "content": f"no tool {calls[i]['name']!r}"} if t is None else run_tool(t, calls[i].get("args", {}))

    return [{"role": "tool", "name": calls[i]["name"], **out[i]} for i in range(len(calls))]
