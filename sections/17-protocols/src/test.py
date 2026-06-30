"""Section 17 offline checks: a request is recorded pending with a correlation
id, the shutdown and plan-approval flows resolve to approved or rejected, a reply
to an unknown id is ignored, a wrong reply type cannot resolve a request
(type-confusion guard), a duplicate reply is a no-op, and an unanswered request
stays pending. Runs over a real Team in a temp dir. No key, no network.

    python sections/17-protocols/src/test.py
"""
import tempfile

import mailbox
from protocols import APPROVED, PENDING, REJECTED, Protocol


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


if __name__ == "__main__":
    test()
