"""Coordination (section 16): a team of named inboxes so several agents can run
at once and talk. Introduced in section 16, then carried forward unchanged.

A large job exceeds one context window, so it fans out across teammates. They
need three things a lone loop lacks: addressing (stable names), a channel (a way
to deliver a message the recipient will see), and escalation (a teammate hitting
a gated action must reach a human, not stall or self-approve).

Each agent owns an inbox: one JSON file per teammate under a shared team dir.
To talk you append to the recipient's inbox under a file lock, so concurrent
senders serialize; `to="*"` broadcasts. There is no broker. Delivery is the
recipient draining its own inbox and folding new messages into its next turn
(the poll-and-fold model: an agent never hard-blocks on a peer). Permission
requests ride the same channel: a teammate sends a permission_request, the lead
routes it to a human, and the verdict returns as a permission_response.

ponytail: one fcntl lock around the whole team (proper-lockfile's analog); split
to per-inbox locks only if a large roster makes that one lock a bottleneck.
"""
from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path


class Team:
    """A roster of named inboxes under `root`/inboxes, one JSON file each.
    The roster is closed: you can only address a registered teammate, which is
    also the trust boundary (a name becomes a path, so it must be known)."""

    def __init__(self, root, members):
        self.dir = Path(root) / "inboxes"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.members = list(members)
        for m in self.members:
            self._path(m).write_text("[]")          # empty inbox per teammate

    def send(self, frm, to, content):
        """Append a message to the recipient's inbox; to='*' broadcasts to every
        teammate but the sender. One lock serializes concurrent senders."""
        targets = [m for m in self.members if m != frm] if to == "*" else [self._check(to)]
        with self._lock():
            for t in targets:
                inbox = self._read(t)
                inbox.append({"from": self._check(frm), "to": t, "content": content})
                self._path(t).write_text(json.dumps(inbox))

    def drain(self, name):
        """Read and clear a teammate's inbox, oldest first. Delivery is the
        recipient draining its own inbox, so a peer never blocks waiting on it."""
        with self._lock():
            inbox = self._read(name)
            self._path(name).write_text("[]")
            return inbox

    # --- disk plumbing ---
    def _check(self, name):
        if name not in self.members:                # closed roster = the trust boundary
            raise ValueError(f"not a teammate: {name!r}")
        return name

    def _path(self, name):
        return self.dir / f"{self._check(name)}.json"

    def _read(self, name):
        return json.loads(self._path(name).read_text())

    @contextmanager
    def _lock(self):
        f = open(self.dir / ".lock", "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX)           # blocks until the other sender releases
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
            f.close()


def fold_inbox(messages, team, name):
    """Drain `name`'s inbox and surface chat (string) messages on its next turn,
    so a teammate folds peers' messages in between turns instead of blocking on
    them. Mirrors how background completions (section 13) prepend to the next
    turn. Returns every drained message (not just chat), so a structured message
    is never silently lost; the caller routes the rest (e.g. permission replies)."""
    drained = team.drain(name)
    chat = [m for m in drained if isinstance(m["content"], str)]
    if chat and messages and isinstance(messages[-1].get("content"), str):
        note = "\n".join(f"<message from={m['from']!r}>{m['content']}</message>" for m in chat)
        messages[-1]["content"] = note + "\n\n" + messages[-1]["content"]
    return drained


def bubbling_approver(team, me, lead, human):
    """An approver (section 3) for a teammate with no human in its own loop: a
    gated call escalates to the lead. The request and the verdict both travel the
    inbox channel; the lead's approval UI (`human`) decides. The teammate returns
    on what it reads back from its own inbox, so the answer is an inbox message,
    not a direct call. ponytail: synchronous round-trip; the real bus polls async."""
    def approve(name, args):
        team.send(me, lead, {"kind": "permission_request", "tool": name, "args": args})
        verdict = human(name, args)                 # the lead routes it to its approval UI
        team.send(lead, me, {"kind": "permission_response", "tool": name, "ok": verdict})
        responses = [m["content"] for m in team.drain(me)
                     if isinstance(m["content"], dict) and m["content"].get("kind") == "permission_response"]
        return bool(responses and responses[-1]["ok"])
    return approve
