"""Section 17 offline checks: a request is recorded pending with a correlation
id, the shutdown and plan-approval flows resolve to approved or rejected, a reply
to an unknown id is ignored, a wrong reply type cannot resolve a request
(type-confusion guard), a duplicate reply is a no-op, and an unanswered request
stays pending.

test_run_teammate(): a self-running teammate is stopped by the handshake, not a
daemon kill. run_teammate works a chat task, then confirms a shutdown_request and
returns, and the lead resolves the echoed shutdown_approved to APPROVED.

Runs over a real Team in a temp dir. No key, no network.

    python sections/17-protocols/src/test.py
"""
import tempfile
import time

import background
import mailbox
from protocols import APPROVED, PENDING, REJECTED, Protocol, protocol_tools, run_teammate


def test():
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", "worker"])
        lead = Protocol(team, "lead")
        worker = Protocol(team, "worker")

        # unknown request types have no reply contract, so they are refused
        try:
            lead.request("worker", "demolish_request"); assert False
        except ValueError:
            pass

        # shutdown: lead requests, the request lands typed with a correlation id
        rid = lead.request("worker", "shutdown_request", reason="done")
        assert lead.pending[rid]["state"] == PENDING
        inbox = team.drain("worker")
        assert inbox[0]["content"] == {"type": "shutdown_request", "request_id": rid, "reason": "done"}

        # the worker confirms; the echoed id resolves exactly that pending request
        worker.reply(inbox[0], "shutdown_approved")
        reply = team.drain("lead")[0]
        assert lead.resolve(reply) == APPROVED
        assert lead.pending[rid]["state"] == APPROVED

        # a duplicate reply for an already resolved id is ignored (idempotent)
        assert lead.resolve(reply) is None

        # shutdown can also be rejected
        lead.request("worker", "shutdown_request", reason="stop")
        req = team.drain("worker")[0]
        worker.reply(req, "shutdown_rejected")
        assert lead.resolve(team.drain("lead")[0]) == REJECTED

        # plan approval is the same shape, inverted: worker requests, lead approves,
        # and the approval carries the permission mode the work runs under
        worker.request("lead", "plan_approval_request", plan="rename foo to bar")
        ask = team.drain("lead")[0]
        lead.reply(ask, "plan_approval_response", approved=True, permissionMode="acceptEdits")
        ans = team.drain("worker")[0]
        assert worker.resolve(ans) == APPROVED
        assert ans["content"]["permissionMode"] == "acceptEdits"

        # a rejected plan resolves to REJECTED
        worker.request("lead", "plan_approval_request", plan="rm -rf build")
        ask2 = team.drain("lead")[0]
        lead.reply(ask2, "plan_approval_response", approved=False)
        assert worker.resolve(team.drain("worker")[0]) == REJECTED

        # type-confusion guard: a plan reply cannot resolve a shutdown request
        rid4 = lead.request("worker", "shutdown_request", reason="x")
        team.drain("worker")
        wrong = {"from": "worker", "to": "lead",
                 "content": {"type": "plan_approval_response", "request_id": rid4, "approved": True}}
        assert lead.resolve(wrong) is None
        assert lead.pending[rid4]["state"] == PENDING        # an unanswered request stays pending

        # a reply for an id we never issued is ignored
        stray = {"from": "worker", "to": "lead",
                 "content": {"type": "shutdown_approved", "request_id": "nobody-9"}}
        assert lead.resolve(stray) is None

    print("17 protocols: ok")


def test_tools():
    """The handshakes driven through the tools (standing in for the model's tool
    calls), resolved by the harness. The decision is a tool call; correlation and
    resolve stay in the protocol layer."""
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", "worker"])
        worker, lead = Protocol(team, "worker"), Protocol(team, "lead")
        w = {t.name: t for t in protocol_tools(worker, lead="lead")}
        l = {t.name: t for t in protocol_tools(lead, lead="lead")}

        # worker submits a plan; the lead notes the inbound request and approves it
        w["ExitPlanMode"].run({"plan": "rename foo to bar across the repo"})
        for m in team.drain("lead"):
            lead.note_inbound(m)
        l["ApprovePlan"].run({"approved": True, "permissionMode": "acceptEdits"})
        assert next(filter(None, (worker.resolve(m) for m in team.drain("worker"))), None) == APPROVED

        # lead asks the worker to stop; StopTeammate puts a correlated shutdown_request
        # on the wire. The worker confirms via its run_teammate loop (harness-driven),
        # covered by test_run_teammate, so here we check the request the tool sent.
        l["StopTeammate"].run({"name": "worker", "reason": "done"})
        req = team.drain("worker")[0]["content"]
        assert req["type"] == "shutdown_request" and req["request_id"] and req["reason"] == "done"

        # a rejected plan resolves to REJECTED through the same ApprovePlan tool
        w["ExitPlanMode"].run({"plan": "rm -rf build"})
        for m in team.drain("lead"):
            lead.note_inbound(m)
        l["ApprovePlan"].run({"approved": False})
        assert next(filter(None, (worker.resolve(m) for m in team.drain("worker"))), None) == REJECTED

        # ApprovePlan with nothing recorded is a harmless no-op, not a crash
        fresh = {t.name: t for t in protocol_tools(Protocol(team, "lead"), lead="lead")}
        assert fresh["ApprovePlan"].run({"approved": True}) == "no plan is awaiting approval"

    print("17 protocols: tools ok")


def test_run_teammate():
    """A spawned teammate (section 16) is stopped by the handshake, not a daemon
    kill: run_teammate works a chat task, then confirms a shutdown_request and
    returns, and the lead resolves the echoed shutdown_approved to APPROVED."""
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", "worker"])
        runtime = background.Runtime()
        seen = []

        runtime.start(lambda: run_teammate(team, "worker", "lead",
                                           lambda prompt: seen.append(prompt), max_idle_polls=200))

        team.send("lead", "worker", "do a small thing")     # a task lands as chat
        for _ in range(200):                                # let the teammate work it before we stop it
            if seen:
                break
            time.sleep(0.01)

        lead = Protocol(team, "lead")
        lead.request("worker", "shutdown_request", reason="done")   # ask for a clean stop
        state = None
        for _ in range(200):                                # wait for the teammate to confirm and exit
            state = next(filter(None, (lead.resolve(m) for m in team.drain("lead")
                                       if isinstance(m["content"], dict))), None)
            if state:
                break
            time.sleep(0.01)

        assert state == APPROVED, state
        assert seen and "do a small thing" in seen[0]       # the chat task ran, folded, before the stop

    print("17 protocols: run_teammate ok")


if __name__ == "__main__":
    test()
    test_tools()
    test_run_teammate()
