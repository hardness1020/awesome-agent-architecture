"""Section 14 offline checks: the clock fires due tasks, recurring re-arms,
one-shots auto-delete, and durable tasks survive a restart. A fake clock makes
it deterministic with no real waiting. No key, no network.

    python sections/14-scheduling/src/test.py
"""
import tempfile
from pathlib import Path

from scheduler import Scheduler


def test():
    now = [1000.0]                                         # a fake clock we advance by hand
    sched = Scheduler(clock=lambda: now[0])

    # nothing is due yet: a future one-shot and a recurring task both stay quiet
    one = sched.create("run the report", due=1005.0)
    rec = sched.create("poll CI", due=1002.0, every=30.0)
    sched.tick()
    assert sched.drain() == []                             # onFire never ran
    assert len(sched.list()) == 2

    # advance past the recurring task's due time: it fires and re-arms, the one-shot still waits
    now[0] = 1003.0
    sched.tick()
    assert sched.drain() == ["poll CI"]                    # fired = enqueued, not run inline
    assert len(sched.list()) == 2                          # recurring task is still registered
    next_due = {t["id"]: t["due"] for t in sched.list()}[rec]
    assert next_due == 1033.0                              # re-armed to now + every

    # same clock, another tick: the recurring task does not double-fire
    sched.tick()
    assert sched.drain() == []

    # advance past the one-shot: it fires once, then auto-deletes (recurring re-armed to 1033, not due)
    now[0] = 1006.0
    sched.tick()
    assert sched.drain() == ["run the report"]
    assert one not in {t["id"] for t in sched.list()}      # one-shot gone
    assert rec in {t["id"] for t in sched.list()}          # recurring stays

    # durability: a durable task persists; a new Scheduler on the same path reloads it
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "scheduled_tasks.json"
        s1 = Scheduler(path=path, clock=lambda: now[0])
        s1.create("nightly backup", due=2000.0, every=86400.0, durable=True)
        s1.create("ephemeral", due=2000.0)                 # not durable: stays in memory only
        assert "ephemeral" not in path.read_text()

        s2 = Scheduler(path=path, clock=lambda: now[0])     # "restart": reload from disk
        reloaded = s2.list()
        assert len(reloaded) == 1 and reloaded[0]["prompt"] == "nightly backup"
        assert s2.create("x", due=2000.0) == 2              # _next resumed past the reloaded id

    print("14 scheduling: ok")


if __name__ == "__main__":
    test()
