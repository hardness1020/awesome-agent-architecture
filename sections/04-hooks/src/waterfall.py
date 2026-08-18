"""Waterfall hooks (section 4, contrast demo): deepseek-harness's hook style.

In dsh a hook is a plain function on a named event inside the harness
process, not a shell subprocess. Hooks form a chain and each receives
(payload, next). Returning without calling next() owns the decision; calling
next() lets the rest of the chain decide, then may adjust that result.
Bridged shell hooks merge strictest-wins: deny > ask > allow, so ordering
cannot loosen a decision.

Standalone on purpose: not wired into _dispatch, so later sections carry the
same loop forward. Mirrors dsh docs/cordis-primer.md and the hook-protocol
merge at dsh-v0.1.0-rc.7.
"""
from __future__ import annotations

DENY, ASK, ALLOW = "deny", "ask", "allow"
_RANK = {DENY: 0, ASK: 1, ALLOW: 2}


class Waterfall:
    """One typed event. dispatch() runs the listener chain front to back."""

    def __init__(self):
        self._listeners = []

    def on(self, fn):
        self._listeners.append(fn)

    def dispatch(self, payload, default=ALLOW):
        def call(i):
            if i == len(self._listeners):
                return default
            return self._listeners[i](payload, lambda: call(i + 1))

        return call(0)


def merge(decisions):
    """Fold bridged hook outputs most-restrictively: deny > ask > allow."""
    return min(decisions, key=_RANK.__getitem__, default=ALLOW)
