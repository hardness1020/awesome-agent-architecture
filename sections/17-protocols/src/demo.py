"""Section 17 demo: two protocol round trips over the section-16 channel. The
worker uses the model to draft a one-line plan, then asks the lead to approve it
before any work starts; the lead approves and pins the permission mode the work
runs under. With the plan gated, the lead stops the worker with a shutdown
handshake: it asks, the worker flushes and confirms, and the lead resolves the
stop cleanly instead of killing the thread mid-flight.

The loop and the subagent path are unchanged (section 16 kept them too):
protocols layer typed request/reply on the channel, so the model only writes the
plan text; protocols.py shapes, correlates, and resolves the exchanges. The state
machine and its guards are proven offline in test.py. Runs in a throwaway temp
dir, so it never touches this repo.

    uv run python sections/17-protocols/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import tempfile

from anthropic import Anthropic
from dotenv import load_dotenv

import mailbox
import protocols
from loop import Session, run_turn
from tools import Registry

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = ("You are 'worker', a teammate on a small agent team. Reply with one short line only, "
          "no preamble.")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("17 protocols: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system or SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=256)

    with tempfile.TemporaryDirectory() as root:
        team = mailbox.Team(root, ["lead", "worker"])
        lead = protocols.Protocol(team, "lead")
        worker = protocols.Protocol(team, "worker")

        # the worker drafts a plan with the model (no tools needed: it is just text)
        messages = [{"role": "user",
                     "content": "Propose in one line how you would rename the function foo to bar across a repo."}]
        plan = run_turn(messages, model, Registry(), Session())
        print("17 protocols: worker plan:", plan)

        # plan approval: the worker requests, the lead approves before work starts
        worker.request("lead", "plan_approval_request", plan=plan)
        ask = next(m for m in team.drain("lead") if m["content"]["type"] == "plan_approval_request")
        print("17 protocols: lead reviews the plan; approving (acceptEdits)")
        lead.reply(ask, "plan_approval_response", approved=True, permissionMode="acceptEdits")
        state = next(filter(None, (worker.resolve(m) for m in team.drain("worker"))), None)
        print("17 protocols: plan", state)                  # -> approved

        # shutdown: the lead asks, the worker flushes and confirms, the lead resolves
        lead.request("worker", "shutdown_request", reason="task done")
        req = next(m for m in team.drain("worker") if m["content"]["type"] == "shutdown_request")
        print("17 protocols: worker flushing state, then confirming stop")
        worker.reply(req, "shutdown_approved")
        stop = next(filter(None, (lead.resolve(m) for m in team.drain("lead"))), None)
        print("17 protocols: shutdown", stop)               # -> approved, a clean stop


if __name__ == "__main__":
    demo()
