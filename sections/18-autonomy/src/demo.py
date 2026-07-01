"""Section 18 demo: a model-driven coordinator. The lead is a normal run_turn loop
with tools, and it takes ONE active step: it decides the team and the work by
calling TeamCreate (form the team), TaskCreate (post the board), and SpawnTeammate
(start the workers). After that the lead is done. There is a single run_turn in
demo(), the lead's; each worker's own run_turn lives in spawn_worker (module
level), reached only through the spawn tool. The harness does not create the team,
set up threads, assign tasks, or send stops by hand.

Everything after the spawn is the workers' own doing. Each spawned worker runs its
own autonomy loop (run_teammate) on a thread: it claims a task from the shared
board, does it with the model, marks it completed, and when the board is empty it
stops itself, reporting done through section 13's notification queue. So forming
and spawning are the lead's decisions, and pulling work and deciding when to stop
are each worker's. The main process only waits for the workers to wind down.

Self-stop fits a known, finite board (posted up front here). A dynamic board,
where more tasks may still arrive, instead keeps idle workers alive and ends them
with the section-17 shutdown handshake; that path is covered in test.py. The
deterministic proofs (the claim race, the spawn tool, TeamCreate) are offline in
test.py too. Runs in a throwaway temp dir, so it never touches this repo.

    uv run python sections/18-autonomy/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import tempfile
import time

from anthropic import Anthropic
from dotenv import load_dotenv

import autonomy
import background
import mailbox
from autonomy import run_teammate
from loop import Session, run_turn
from permissions import DEFAULT
from tasks import TaskStore, task_tools
from tools import Registry

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
LEAD_SYSTEM = ("You are the team lead. You have a shared task board and two workers you can spawn, "
               "worker-1 and worker-2. Form your team before spawning. Use your tools to coordinate. "
               "Be brief, no preamble.")
WORKER_SYSTEM = ("You are an autonomous worker. Do the task you are given in one short line, then "
                 "call TaskUpdate to mark it completed. Be brief.")
WORKERS = ["worker-1", "worker-2"]
LEAD_ALLOW = {"TeamCreate", "SendMessage", "TaskCreate", "TaskList", "TaskGet", "SpawnTeammate"}
WORKER_ALLOW = {"TaskUpdate", "TaskList", "TaskGet"}
IDLE_STOP = 20    # empty polls before an idle worker stops itself (the board is a known, finite batch)


def spawn_worker(name, formed, store, model):
    """One autonomous worker: claim tasks off the board, do each with the model,
    stop itself when the board drains. This is the worker's own run_turn, reached
    only when the lead calls SpawnTeammate, so demo() runs only the lead."""
    team = formed["team"]
    if team is None:                                   # spawned before the lead formed the team
        return "shutdown"
    reg = Registry()
    for t in task_tools(store):
        if t.name != "TaskCreate":                     # workers update and read the board; only the lead posts
            reg.register(t)

    def work(prompt, task):
        run_turn([{"role": "user", "content": prompt}], lambda m, r, s: model(m, r, WORKER_SYSTEM),
                 reg, Session(mode=DEFAULT, allow_rules=set(WORKER_ALLOW)))
        if task is not None and (store.get(task["id"]) or {}).get("status") != "completed":
            store.update(task["id"], status="completed")    # safety net so the board can drain
        print(f"18 autonomy: {name} finished task {task['id'] if task else '-'}")

    return run_teammate(team, store, name, "lead", work, max_idle_polls=IDLE_STOP)  # self-stop


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("18 autonomy: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system, messages=messages,
                                       tools=registry.schemas(), max_tokens=512)

    with tempfile.TemporaryDirectory() as root:
        store = TaskStore(os.path.join(root, "tasks"))
        runtime = background.Runtime()
        formed = {"team": None}                        # TeamCreate fills this; the script never does

        # lead config: post the board, form the team, spawn workers. That is all the lead does.
        lead_reg = Registry()
        for t in task_tools(store):
            if t.name in ("TaskCreate", "TaskList", "TaskGet"):
                lead_reg.register(t)
        for t in mailbox.team_tools(root, "lead", formed):     # TeamCreate + SendMessage
            lead_reg.register(t)
        for t in mailbox.teammate_tools(runtime, lambda name: spawn_worker(name, formed, store, model)):
            lead_reg.register(t)

        # The one agent call in demo(): the lead forms the team, posts the board, and spawns.
        run_turn([{"role": "user", "content":
                   "Create your team with worker-1 and worker-2. Then create a task for each of three "
                   "short haikus (one about locks, one about idle loops, one about teams), and spawn "
                   "worker-1 and worker-2 to do them."}],
                 lambda m, r, s: model(m, r, LEAD_SYSTEM), lead_reg,
                 Session(mode=DEFAULT, allow_rules=set(LEAD_ALLOW)))

        if formed["team"] is None:
            print("18 autonomy: the lead did not form a team; nothing to coordinate")
            return
        print("18 autonomy: team:", formed["team"].members)
        print("18 autonomy: board:", [(t["id"], t["subject"], t["status"]) for t in store.list()])

        # Now the workers run themselves: each pulls tasks off the shared board and, when the
        # board is empty, stops itself and reports done through section 13's notification queue.
        # The main process only waits for those notes; it never assigns work or sends a stop.
        stopped = []
        for _ in range(600):
            stopped += [n for n in runtime.drain() if "completed" in n]
            if len(stopped) >= len(WORKERS):
                break
            time.sleep(autonomy.POLL_INTERVAL)
        done = [t["id"] for t in store.list() if t["status"] == "completed"]
        print(f"18 autonomy: {len(stopped)} workers stopped themselves; board drained ({len(done)} tasks done)")


if __name__ == "__main__":
    demo()
