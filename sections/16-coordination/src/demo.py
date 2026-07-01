"""Section 16 demo: one main agent, one run_turn. The lead is a normal loop with
tools, and it takes ONE step: it decides how big a team the task needs and calls
TeamCreate, spawns each member with SpawnTeammate, then delegates subtasks with
SendMessage. The script fixes neither the team size nor the names; the lead does.
The harness does not hand-start a worker or script its turns.

SpawnTeammate runs a teammate's serve_mailbox loop on a background thread (section
13); from there the teammate pulls its own inbox, does each task with the shell (a
gated call that bubbles a permission_request to the lead's UI), and reports back
with SendMessage, all on its own thread. So there is a single run_turn in demo(),
the lead's. The teammate's own run_turn lives in spawn_worker (module level),
reached only through the lead's spawn tool call, never driven by the script.

Neither agent calls the other directly; the inbox is the only link. The channel's
no-loss guarantee, the mailbox loop, and the TeamCreate, SendMessage, and
SpawnTeammate tools are proven offline in test.py. Runs in a throwaway temp dir.

    uv run python sections/16-coordination/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
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
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
LEAD_SYSTEM = ("You are the team lead. First decide how many teammates the task needs and create your "
               "team with TeamCreate. Then spawn each teammate with SpawnTeammate and delegate a "
               "subtask to each with SendMessage. Report what comes back. Be brief.")
WORKER_SYSTEM = ("You are a teammate. Do the task in your inbox using the shell, then call SendMessage "
                 "to report your one-line result to the lead. Be brief.")
IDLE_STOP = 40    # empty mailbox polls before a spawned teammate winds down (no shutdown protocol yet; that is section 17)


def sh(a):
    return subprocess.run(a["command"], shell=True, capture_output=True, text=True, timeout=60).stdout.strip()


def lead_ui(name, args):
    print(f"16 coordination: worker asks to run {name} {args}; lead approves")
    return True


def spawn_worker(name, formed, model):
    """One teammate: pull the mailbox, do each task with the model, reply. This is
    the teammate's own run_turn, reached only when the lead calls SpawnTeammate, so
    demo() itself runs only the lead. The team is whatever the lead formed with
    TeamCreate, read from `formed` at spawn time. Bash bubbles to the lead's UI;
    SendMessage carries the result back over the same inbox channel."""
    team = formed["team"]
    if team is None:                                   # spawned before the lead formed the team
        return "no team yet"
    reg = Registry()
    reg.register(Tool("Bash", sh, description="Run a shell command.",
                      input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                                    "required": ["command"]}))
    for t in mailbox.message_tools(team, name):
        reg.register(t)

    def work(prompt):
        run_turn([{"role": "user", "content": prompt}], lambda m, r, s: model(m, r, WORKER_SYSTEM), reg,
                 Session(mode=DEFAULT, allow_rules={"SendMessage"}),   # Bash bubbles; SendMessage is free
                 approver=mailbox.bubbling_approver(team, name, "lead", human=lead_ui))

    return mailbox.serve_mailbox(team, name, work, max_idle_polls=IDLE_STOP)   # pulls its own inbox on this thread


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("16 coordination: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system, messages=messages,
                                       tools=registry.schemas(), max_tokens=512)

    with tempfile.TemporaryDirectory() as root:
        formed = {"team": None}                        # TeamCreate fills this; the script never does
        runtime = background.Runtime()

        # lead config: form a team, spawn its members, delegate. That is all the lead does.
        lead_reg = Registry()
        for t in mailbox.team_tools(root, "lead", formed):     # TeamCreate + SendMessage
            lead_reg.register(t)
        for t in mailbox.teammate_tools(runtime, lambda name: spawn_worker(name, formed, model)):
            lead_reg.register(t)

        # The one agent call in demo(): the lead sizes its team, spawns it, and delegates.
        goal = ("Collect three facts about this machine using the shell: today's date, the current "
                "working directory, and the OS name (uname -s). Decide how many teammates the work "
                "needs, create your team, spawn them, and delegate the facts with SendMessage.")
        run_turn([{"role": "user", "content": goal}], lambda m, r, s: model(m, r, LEAD_SYSTEM), lead_reg,
                 Session(mode=DEFAULT, allow_rules={"TeamCreate", "SendMessage", "SpawnTeammate"}))

        team = formed["team"]
        if team is None:
            print("16 coordination: the lead did not form a team; nothing to coordinate")
            return
        print("16 coordination: team is", team.members)

        # The teammates now run themselves: each pulls its inbox, does the task, and
        # reports back. The number of replies is the lead's choice, not the script's;
        # collect them until a quiet gap. The main process only waits.
        replies, quiet = [], 0
        for _ in range(1200):
            chat = [m["content"] for m in team.drain("lead") if isinstance(m["content"], str)]
            replies += chat
            quiet = 0 if chat else quiet + 1
            if replies and quiet >= 20:                # got replies, then a quiet gap: done
                break
            time.sleep(0.05)
        for r in replies:
            print("16 coordination -> lead heard:", r)
        if not replies:
            print("16 coordination -> lead heard: (no reply)")


if __name__ == "__main__":
    demo()
