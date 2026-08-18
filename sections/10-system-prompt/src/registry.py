"""Prompt section registry (section 10): the deepseek-harness contrast.

prompt.py assembles one fixed list in file order, so anything that wants a new
section has to edit that list. dsh keeps a registry instead. A plugin registers a
named section with a numeric order, an agent-scoped section shadows a global one
of the same name, and assembly sorts by order. Text renders through strict
{{variable}} interpolation: an unknown name raises rather than shipping a prompt
with a hole in it.

This is a contrast demo. It is not wired into assemble(), so later sections carry
prompt.py forward unchanged.
"""
from __future__ import annotations

import re

HARNESS, PERSONA, TOOLS = -100, 0, 100   # the order bands dsh uses by convention


class PromptRegistry:
    """Named sections and variables, per scope, assembled in numeric order."""

    def __init__(self):
        self._sections: dict[tuple, tuple] = {}    # (scope, name) -> (order, text)
        self._variables: dict[tuple, str] = {}     # (scope, name) -> value

    def section(self, name, text, order=PERSONA, scope=None) -> None:
        self._sections[(scope, name)] = (order, text)

    def variable(self, name, value, scope=None) -> None:
        self._variables[(scope, name)] = value

    def assemble(self, scope=None) -> str:
        """One prompt for this scope: a scoped section shadows the global one of that name."""
        chosen: dict[str, tuple] = {}
        for (sec_scope, name), entry in self._sections.items():
            if sec_scope is not None and sec_scope != scope:
                continue                          # belongs to another agent
            if sec_scope is not None or name not in chosen:
                chosen[name] = entry              # a scoped section shadows the global one
        variables = {n: v for (s, n), v in self._variables.items() if s is None}
        variables.update({n: v for (s, n), v in self._variables.items() if s is not None and s == scope})
        ordered = sorted(chosen.values(), key=lambda e: e[0])
        return "\n\n".join(render(text, variables) for _order, text in ordered)


def render(text, variables) -> str:
    """Strict {{name}} interpolation. An unknown name raises; nothing renders empty."""
    def sub(match):
        name = match.group(1).strip()
        if name not in variables:
            raise KeyError(f"unknown prompt variable {name!r}")
        return str(variables[name])
    return re.sub(r"\{\{([^{}]*)\}\}", sub, text)
