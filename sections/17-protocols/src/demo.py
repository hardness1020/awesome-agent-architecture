"""Section 17 demo: one main agent, one run_turn, and a graceful stop. The lead is
a normal loop with tools. It spawns a self-running teammate (section 16), delegates
a one-line task with SendMessage, then asks the teammate to stop cleanly with
StopTeammate. The teammate is not killed: its run_teammate loop confirms the
shutdown_request with shutdown_approved and returns, so the stop is a handshake
(section 17), not a daemon dying with the process.

There is a single run_turn in demo(), the lead's. The teammate's own run_turn
lives in spawn_worker (module level), reached only through the lead's spawn tool
call. The lead decides to spawn, delegate, and stop; the teammate confirms the
stop on its own thread. The plan-approval handshake is the symmetric inverse (the
teammate requests, the lead approves) and is proven offline in test.py, along with
the correlation and state-machine logic. Runs in a throwaway temp dir.

    uv run python sections/17-protocols/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import subprocess
import tempfile
import time

from anthropic import Anthropic
from dotenv import load_dotenv

import background
import mailbox
from loop import Session, run_turn
from permissions import DEFAULT
from protocols import Protocol, protocol_tools, run_teammate
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
LEAD_SYSTEM = ("You are the team lead. Spawn a teammate, delegate a one-line task with SendMessage, "
               "then ask the teammate to stop cleanly with StopTeammate. Be brief.")
WORKER_SYSTEM = "You are a teammate. Do the task in your inbox using the shell in one line. Be brief."
IDLE_STOP = 200   # backstop: the teammate stops on the handshake; this only bounds a demo where no stop arrives


def sh(a):
    return subprocess.run(a["command"], shell=True, capture_output=True, text=True, timeout=60).stdout.strip()


def spawn_worker(name, team, model):
    """One teammate: pull the mailbox and do each task, but stop on the lead's
    shutdown handshake (run_teammate, section 17). This is the teammate's own
    run_turn, reached only when the lead calls SpawnTeammate, so demo() runs only
    the lead."""
    reg = Registry()
    reg.register(Tool("Bash", sh, description="Run a shell command.",
                      input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                                    "required": ["command"]}))

    def work(prompt):
        run_turn([{"role": "user", "content": prompt}], lambda m, r, s: model(m, r, WORKER_SYSTEM), reg,
                 Session(mode=DEFAULT, allow_rules={"Bash"}))

    return run_teammate(team, name, "lead", work, max_idle_polls=IDLE_STOP)


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("17 protocols: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system, messages=messages,
                                       tools=registry.schemas(), max_tokens=512)

    with tempfile.TemporaryDirectory() as root:
        team = mailbox.Team(root, ["lead", "worker-1"])    # roster is config; section 16 shows the model forming it
        runtime = background.Runtime()
        lead_proto = Protocol(team, "lead")                # the lead's request tracker (StopTeammate uses it)

        # lead config: the handshake tools, SendMessage to delegate, and SpawnTeammate.
        lead_reg = Registry()
        for t in protocol_tools(lead_proto, lead="lead"):
            lead_reg.register(t)
        for t in mailbox.message_tools(team, "lead"):
            lead_reg.register(t)
        for t in mailbox.teammate_tools(runtime, lambda name: spawn_worker(name, team, model)):
            lead_reg.register(t)

        # The one agent call in demo(): the lead spawns a teammate, delegates, and stops it.
        goal = ("Spawn a teammate named worker-1. Send it a one-line task with SendMessage: run the "
                "`date` command. Then ask worker-1 to stop cleanly with StopTeammate.")
        run_turn([{"role": "user", "content": goal}], lambda m, r, s: model(m, r, LEAD_SYSTEM), lead_reg,
                 Session(mode=DEFAULT, allow_rules={"SendMessage"}))   # StopTeammate/SpawnTeammate are read-only

        # The teammate ran itself and confirmed the stop on its own thread. Resolve
        # the lead's side of the handshake from its inbox. The main process only waits.
        state = None
        for _ in range(600):
            state = next(filter(None, (lead_proto.resolve(m) for m in team.drain("lead")
                                       if isinstance(m["content"], dict))), None)
            if state:
                break
            time.sleep(0.05)
        print("17 protocols: worker stop ->", state)       # -> approved


if __name__ == "__main__":
    demo()
