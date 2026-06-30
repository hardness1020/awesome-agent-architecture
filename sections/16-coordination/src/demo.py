"""Section 16 demo: a two-agent team passing work over inboxes. The lead drops a
task into the worker's inbox; we fold it into the worker's turn so the model
sees it. The worker's shell is gated, so its call bubbles a permission_request to
the lead, whose UI (here auto-approve) answers over the same channel; then the
worker sends its result back to the lead's inbox.

The loop and the subagent path are unchanged (section 14 kept the loop too):
coordination wraps a turn from outside by draining the inbox before it and
passing a bubbling approver into it. The concurrent no-loss case is proven
offline in test.py. Runs in a throwaway temp dir, so it never touches this repo.

    uv run python sections/16-coordination/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import subprocess
import tempfile

from anthropic import Anthropic
from dotenv import load_dotenv

import mailbox
from loop import Session, run_turn
from permissions import DEFAULT
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = ("You are 'worker', a teammate on a small agent team. Do the task in your inbox "
          "using the shell, then answer in one line so the lead can read it.")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("16 coordination: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system or SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=512)

    def sh(a):
        return subprocess.run(a["command"], shell=True, capture_output=True, text=True,
                              timeout=60).stdout.strip()

    with tempfile.TemporaryDirectory() as root:
        team = mailbox.Team(root, ["lead", "worker"])
        reg = Registry()
        reg.register(Tool("Bash", sh, description="Run a shell command.",
                          input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                                        "required": ["command"]}))

        # the lead addresses the worker over its inbox
        team.send("lead", "worker", "Print the current date with the shell and tell me what it is.")
        print("16 coordination: lead -> worker inbox; folding it into the worker's turn...")

        # the worker has no human in its loop, so a gated call bubbles to the lead's UI
        def lead_ui(name, args):
            print(f"16 coordination: worker asks to run {name} {args}; lead approves")
            return True

        session = Session(mode=DEFAULT)                    # Bash not pre-allowed -> the gate asks
        messages = [{"role": "user", "content": "Check your inbox and act on it."}]
        mailbox.fold_inbox(messages, team, "worker")       # peers' messages surface on this turn
        out = run_turn(messages, model, reg, session,
                       approver=mailbox.bubbling_approver(team, "worker", "lead", human=lead_ui))

        team.send("worker", "lead", out)                   # the worker reports back over the channel
        inbox = team.drain("lead")                          # the lead also holds the spent permission_request
        reply = next((m["content"] for m in inbox if isinstance(m["content"], str)), "(none)")
        print("16 coordination -> lead inbox:", reply)


if __name__ == "__main__":
    demo()
