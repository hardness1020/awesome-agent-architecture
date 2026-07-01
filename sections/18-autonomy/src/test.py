"""Section 18 offline checks, no key, no network.

test(): the single-worker mechanism. claim_next takes the first ready task and
skips a blocked one; a claim race has one winner; next_action prioritizes a
shutdown over chat, folds chat lead-before-peers, and claims when the inbox is
empty; a lead-less worker drains a board and stops cleanly on a shutdown.

test_claim_race(): the lock proof. N threads pile into claim() on the SAME task
at one instant (a barrier forces the overlap); TaskStore.claim's file lock must
yield exactly one winner. With the lock disabled this fails, so it is not vacuous.

test_team_tools(): forming the team is the model's decision. SendMessage stays
inert until TeamCreate materializes the roster (creator included); the lead in
the demo forms its team this way instead of the script pre-creating it.

test_concurrent(): the faithful pipeline end to end under threads. A lead posts a
board; worker threads each run run_teammate, claiming from the one shared board,
idling when empty, and confirming shutdown. Asserts every task is completed
exactly once and every worker stops via the handshake.

    python sections/18-autonomy/src/test.py
"""
import tempfile
import threading
import time

import background
import mailbox
from autonomy import POLL_INTERVAL, claim_next, next_action, run_teammate
from protocols import APPROVED, Protocol
from tasks import TaskStore


def test():
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", "worker", "peer"])
        store = TaskStore(d + "/tasks")
        worker = Protocol(team, "worker")

        # claim_next takes the first pending, unowned task, oldest first
        t1 = store.create("first")
        t2 = store.create("second")
        got = claim_next(store, "worker")
        assert got["id"] == t1["id"] and got["owner"] == "worker"

        # a blocked task is skipped until its blocker completes
        t3 = store.create("blocked", blocked_by=[t2["id"]])
        assert claim_next(store, "worker")["id"] == t2["id"]   # t2 next; t3 still blocked
        assert claim_next(store, "worker") is None             # only t3 left, still blocked
        store.update(t2["id"], status="completed")
        assert claim_next(store, "worker")["id"] == t3["id"]   # now t3 is ready

        # claim race (single-threaded): two agents, one task, exactly one winner
        race = store.create("contested")
        first = claim_next(store, "a")
        second = claim_next(store, "b")
        assert first["id"] == race["id"] and second is None

        # next_action: a shutdown request beats chat and is confirmed
        team.send("lead", "worker", "please keep going")       # chat, dropped: we are stopping
        team.send("lead", "worker", {"type": "shutdown_request", "request_id": "lead-1", "reason": "stop"})
        kind, payload = next_action(worker, team, store, "worker")
        assert kind == "shutdown" and payload == "stop"
        reply = team.drain("lead")[0]["content"]
        assert reply == {"type": "shutdown_approved", "request_id": "lead-1"}

        # next_action: no shutdown, fold chat lead-before-peers
        team.send("peer", "worker", "from peer")
        team.send("lead", "worker", "from lead")
        kind, payload = next_action(worker, team, store, "worker")
        assert kind == "message"
        assert payload.index("from lead") < payload.index("from peer")

        # next_action: empty inbox, claim a task off the board
        store.create("do work")
        kind, task = next_action(worker, team, store, "worker")
        assert kind == "task" and task["status"] == "in_progress"

        # a lead-less worker drains a fresh board, then gives up after max_idle_polls
        d2 = tempfile.mkdtemp()
        store2 = TaskStore(d2 + "/tasks")
        team2 = mailbox.Team(d2, ["lead", "worker"])
        store2.create("a")
        store2.create("b")

        def work(_prompt, task):
            if task is not None:                                # the inner loop "does" the task
                store2.update(task["id"], status="completed")

        assert run_teammate(team2, store2, "worker", "lead", work, max_idle_polls=3) == "drained"
        assert all(t["status"] == "completed" for t in store2.list())

        # run_teammate stops cleanly on a queued shutdown, leaving the board untouched
        d3 = tempfile.mkdtemp()
        store3 = TaskStore(d3 + "/tasks")
        team3 = mailbox.Team(d3, ["lead", "worker"])
        store3.create("untouched")
        lead = Protocol(team3, "lead")
        lead.request("worker", "shutdown_request", reason="halt")
        assert run_teammate(team3, store3, "worker", "lead", work, max_idle_polls=3) == "shutdown"
        assert store3.list()[0]["status"] == "pending"          # never claimed
        state = next(filter(None, (lead.resolve(m) for m in team3.drain("lead"))), None)
        assert state == APPROVED

    print("18 autonomy: ok")


def test_team_tools():
    """TeamCreate as a tool: forming the team is the lead's decision, not the
    script's. SendMessage is inert until the team exists; TeamCreate materializes
    it (with the creator as a member), and then messages deliver."""
    with tempfile.TemporaryDirectory() as d:
        formed = {"team": None}
        tools = {t.name: t for t in mailbox.team_tools(d, "lead", formed)}

        # SendMessage is inert until the lead forms the team
        assert formed["team"] is None
        assert "no team" in tools["SendMessage"].run({"to": "worker-1", "message": "hi"}).lower()

        # TeamCreate brings the team into being; the creator joins automatically
        tools["TeamCreate"].run({"members": ["worker-1", "worker-2"]})
        assert formed["team"] is not None
        assert set(formed["team"].members) == {"lead", "worker-1", "worker-2"}

        # now SendMessage delivers over the team the model just formed
        tools["SendMessage"].run({"to": "worker-1", "message": "claim a task"})
        assert formed["team"].drain("worker-1")[0]["content"] == "claim a task"

    print("18 autonomy: team tools ok")


def test_claim_race(n_threads=16):
    """Force n_threads to claim the SAME task at one instant. The file lock must
    yield exactly one winner. A barrier guarantees the overlap, so the race is
    really hit (defeat the lock and this assertion fails)."""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(d + "/tasks")
        tid = store.create("one hot task")["id"]
        gate = threading.Barrier(n_threads)
        wins = []                                       # winners; list.append is GIL-atomic

        def contend(me):
            gate.wait()                                 # all threads pile into claim() together
            if store.claim(tid, me)["ok"]:
                wins.append(me)

        threads = [threading.Thread(target=contend, args=(f"w{i}",), daemon=True) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert all(not t.is_alive() for t in threads)
        assert len(wins) == 1, f"expected exactly one winner, got {wins}"
        assert store.get(tid)["owner"] == wins[0] and store.get(tid)["status"] == "in_progress"

    print(f"18 autonomy: claim race ok (1 of {n_threads} threads won the lock)")


def test_concurrent(workers=("worker-1", "worker-2", "worker-3"), n_tasks=9):
    """The faithful pipeline end to end under threads: a lead posts a board,
    worker threads claim/idle/complete, then confirm shutdown. (Single-claim
    correctness under contention is proven by test_claim_race; here the work is
    instant, so this checks the pipeline, not the lock window.)"""
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", *workers])
        store = TaskStore(d + "/tasks")
        claims = []                                     # (worker, task_id) per completion; append is GIL-atomic

        def make_work(me):
            def work(_prompt, task):
                if task is not None:                    # the inner loop "does" the task: mark it done
                    store.update(task["id"], status="completed")
                    claims.append((me, task["id"]))
            return work

        results = {}

        def run_worker(me):
            results[me] = run_teammate(team, store, me, "lead", make_work(me))   # idle until shutdown

        threads = [threading.Thread(target=run_worker, args=(w,), daemon=True) for w in workers]
        for t in threads:
            t.start()                                   # workers start idle: the board is empty

        # the lead posts the board, then waits for it to drain
        ids = [store.create(f"job {i}")["id"] for i in range(n_tasks)]
        lead = Protocol(team, "lead")
        for _ in range(400):                            # backstop wait, not a real cap
            if all((store.get(i) or {}).get("status") == "completed" for i in ids):
                break
            time.sleep(POLL_INTERVAL)

        # board drained: stop every worker with a shutdown handshake
        for w in workers:
            lead.request(w, "shutdown_request", reason="board drained")
        for t in threads:
            t.join(timeout=5)

        assert all(not t.is_alive() for t in threads)           # all workers stopped
        assert all(r == "shutdown" for r in results.values())   # via the handshake, not a kill
        assert sorted(tid for _, tid in claims) == sorted(ids)  # every task completed exactly once
        assert all((store.get(i) or {}).get("status") == "completed" for i in ids)
        approvals = [s for s in (lead.resolve(m) for m in team.drain("lead")) if s == APPROVED]
        assert len(approvals) == len(workers)

    print(f"18 autonomy: concurrent ok ({len(workers)} workers, {n_tasks} tasks)")


def test_spawn_tool(workers=("w1", "w2"), n_tasks=6):
    """SpawnTeammate as a tool: calling it (standing in for the lead's tool call)
    starts a worker loop on the section-13 runtime that claims and completes board
    tasks, then stops on a shutdown. The decision to spawn is the tool call."""
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", *workers])
        store = TaskStore(d + "/tasks")
        runtime = background.Runtime()
        done = []                                       # task ids completed; append is GIL-atomic

        def spawn_worker(name):
            def work(_prompt, task):
                if task is not None:
                    store.update(task["id"], status="completed")
                    done.append(task["id"])
            return run_teammate(team, store, name, "lead", work)

        spawn = {t.name: t for t in mailbox.teammate_tools(runtime, spawn_worker)}["SpawnTeammate"]
        for w in workers:                               # the lead spawns workers by calling the tool
            spawn.run({"name": w})

        ids = [store.create(f"t{i}")["id"] for i in range(n_tasks)]
        lead = Protocol(team, "lead")
        for _ in range(400):
            if all((store.get(i) or {}).get("status") == "completed" for i in ids):
                break
            time.sleep(POLL_INTERVAL)
        for w in workers:
            lead.request(w, "shutdown_request", reason="done")

        approved = 0
        for _ in range(200):                            # wait for the spawned workers to confirm and exit
            for m in team.drain("lead"):
                if lead.resolve(m) == APPROVED:
                    approved += 1
            if approved >= len(workers):
                break
            time.sleep(POLL_INTERVAL)

        assert sorted(done) == sorted(ids)              # every task done exactly once by a spawned worker
        assert approved == len(workers)

    print(f"18 autonomy: spawn tool ok ({len(workers)} spawned, {n_tasks} tasks)")


if __name__ == "__main__":
    test()
    test_team_tools()
    test_claim_race()
    test_concurrent()
    test_spawn_tool()
