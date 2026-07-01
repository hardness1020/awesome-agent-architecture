"""Scheduling (section 14): a clock fires turns on a schedule, no human at the
keyboard. Introduced in section 14, then carried forward unchanged.

A Scheduler holds entries (each a prompt plus a fire time) and ticks on its own
daemon thread, independent of whether the loop is running. When a task is due it
does not call the model: it enqueues the prompt (onFire), and the driver drains
that queue between turns (section 1), so a fired prompt arrives as a new
user-style turn. Recurring tasks re-arm to the next interval, one-shots
auto-delete. Durable tasks persist to JSON and reload on start (section 12), so
a schedule set today re-arms after a restart.

We model "when" as an absolute fire time plus an optional repeat interval, not a
5-field cron string. ponytail: timestamp + interval is the mechanism without a
cron parser; swap in croniter if real cron expressions are needed.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path


class Scheduler:
    """Fires scheduled prompts when the clock catches up to their due time."""

    CHECK_INTERVAL = 1.0                         # tick cadence, like cronScheduler's 1s

    def __init__(self, path=None, clock=time.time):
        self._next = 0
        self._tasks: dict[int, dict] = {}        # id -> {id, prompt, due, every, durable}
        self._pending: queue.Queue = queue.Queue()   # fired prompts waiting for the loop
        self._clock = clock                      # injectable so tests run on a fake clock
        self._path = Path(path) if path else None
        self._stop = threading.Event()
        if self._path and self._path.exists():
            self._load()                         # 12 · reload durable tasks on start

    def create(self, prompt, due=None, every=None, durable=False):
        """Schedule a prompt. due: absolute fire time (default now). every:
        seconds between recurring fires (None = one-shot). durable: persist."""
        self._next += 1
        tid = self._next
        self._tasks[tid] = {"id": tid, "prompt": prompt, "every": every, "durable": durable,
                            "due": due if due is not None else self._clock()}
        self._save()
        return tid

    def list(self):
        return list(self._tasks.values())

    def tick(self):
        """Fire every task whose due time has passed; re-arm recurring, drop one-shots."""
        now = self._clock()
        for tid, t in list(self._tasks.items()):
            if now >= t["due"]:
                self._pending.put(t["prompt"])   # onFire: enqueue, never run the model here
                if t["every"]:
                    t["due"] = now + t["every"]   # recurring: re-arm past now, so 1s ticks fire once
                else:
                    self._tasks.pop(tid, None)    # one-shot: auto-delete after firing
        self._save()

    def drain(self):
        """Every fired prompt waiting so far, oldest first; empties the queue."""
        out = []
        while True:
            try:
                out.append(self._pending.get_nowait())
            except queue.Empty:
                return out

    def run(self):
        """Start the tick thread (daemon, so it never keeps the process alive)."""
        def loop():
            while not self._stop.wait(self.CHECK_INTERVAL):
                self.tick()
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _save(self):
        if self._path:                           # only durable tasks survive a restart
            self._path.write_text(json.dumps([t for t in self._tasks.values() if t["durable"]]))

    def _load(self):
        for t in json.loads(self._path.read_text()):
            self._tasks[t["id"]] = t
            self._next = max(self._next, t["id"])
