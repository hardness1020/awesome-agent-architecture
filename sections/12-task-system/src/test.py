"""Section 12 offline checks: the durable task graph and its claim gate.
No key, no network. Tasks are written to a throwaway temp dir.

    python sections/12-task-system/src/test.py
"""
import tempfile
import threading

from tasks import TaskStore


def test():
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(d)

        # sequential ids, persisted: a record is a file, not a line in the prompt
        schema = store.create("set up schema")
        api = store.create("write the API", blocked_by=[schema["id"]])
        assert (schema["id"], api["id"]) == (1, 2)
        assert store.get(api["id"])["blockedBy"] == [schema["id"]]
        assert store.get(schema["id"])["blocks"] == [api["id"]]   # reverse edge kept in sync

        # the gate is on claim, not create: a blocked task refuses the claim
        assert store.claim(api["id"], "agent-1")["reason"] == "blocked"

        # complete the blocker, then the claim goes through
        store.update(schema["id"], status="completed")
        ok = store.claim(api["id"], "agent-1")
        assert ok["ok"] and store.get(api["id"])["owner"] == "agent-1"

        # claim race: 10 agents go for one task, the lock lets exactly one win
        free = store.create("independent work")
        wins, lock = [], threading.Lock()

        def race(name):
            if store.claim(free["id"], name)["ok"]:
                with lock:
                    wins.append(name)

        threads = [threading.Thread(target=race, args=(f"a{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(wins) == 1, f"expected one winner, got {wins}"

        # a corrupt record is skipped, not fatal to the listing
        (store.root / "99.json").write_text("{ not json")
        assert all(t["id"] != 99 for t in store.list()) and store.get(99) is None

    print("12 tasks: ok")


if __name__ == "__main__":
    test()
