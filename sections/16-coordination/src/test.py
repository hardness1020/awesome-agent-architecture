"""Section 16 offline checks: addressing rejects a non-teammate, a message
lands in the recipient's inbox, '*' broadcasts to everyone but the sender,
concurrent senders never lose a message under the lock, and permission bubbling
carries a request to the lead and the verdict back over the same channel. Uses
real files in a temp dir. No key, no network.

    python sections/16-coordination/src/test.py
"""
import tempfile
import threading
from pathlib import Path

import mailbox


def test():
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", "alice", "bob"])

        # addressing: the roster is the trust boundary, an unknown name is refused
        for bad in (lambda: team.send("lead", "stranger", "hi"),
                    lambda: team.drain("stranger")):
            try:
                bad(); assert False
            except ValueError:
                pass

        # a channel: a message lands in the recipient's inbox, not the sender's
        team.send("lead", "alice", "start on the parser")
        inbox = team.drain("alice")
        assert [m["content"] for m in inbox] == ["start on the parser"]
        assert inbox[0]["from"] == "lead"
        assert team.drain("alice") == []                    # drain clears it
        assert team.drain("lead") == []                     # sender's own inbox untouched

        # broadcast: '*' reaches every teammate but the sender
        team.send("lead", "*", "standup in 5")
        assert len(team.drain("alice")) == 1 and len(team.drain("bob")) == 1
        assert team.drain("lead") == []

        # concurrent senders serialize under the lock: no message is lost
        def spam(frm):
            for i in range(20):
                team.send(frm, "bob", f"{frm}-{i}")
        ts = [threading.Thread(target=spam, args=(s,)) for s in ("lead", "alice")]
        for t in ts: t.start()
        for t in ts: t.join()
        assert len(team.drain("bob")) == 40                 # 2 senders * 20, none dropped

        # fold: chat messages surface on the recipient's next turn
        team.send("lead", "alice", "remember to add tests")
        messages = [{"role": "user", "content": "continue"}]
        folded = mailbox.fold_inbox(messages, team, "alice")
        assert len(folded) == 1
        assert "remember to add tests" in messages[-1]["content"]
        assert messages[-1]["content"].endswith("continue")

        # permission bubbling: a gated call escalates to the lead, the verdict
        # returns over the inbox channel (here the lead's UI approves)
        approve = mailbox.bubbling_approver(team, "alice", "lead", human=lambda n, a: True)
        assert approve("Bash", {"command": "ls"}) is True
        request = team.drain("lead")                        # the lead really received the request
        assert request[0]["content"]["kind"] == "permission_request"
        assert request[0]["content"]["tool"] == "Bash"

        deny = mailbox.bubbling_approver(team, "bob", "lead", human=lambda n, a: False)
        assert deny("Bash", {"command": "rm -rf /"}) is False

    print("16 coordination: ok")


if __name__ == "__main__":
    test()
