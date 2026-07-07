"""Section 16 offline checks: addressing rejects a non-teammate, a message
lands in the recipient's inbox, '*' broadcasts to everyone but the sender,
concurrent senders never lose a message under the lock, and permission bubbling
carries a request to the lead and the verdict back over the same channel.

test_serve_mailbox(): a teammate's pull loop drains its inbox, runs work on the
folded message, then winds down when the inbox stays empty.

test_team_tools(): TeamCreate sizes and forms the roster; SendMessage stays inert
until it exists, so forming the team is the lead's decision, not the script's.

test_teammate_tools(): SpawnTeammate as a tool starts a teammate's loop on the
section-13 runtime; the spawned teammate pulls a queued message and replies, so
the decision to add help is the lead's tool call, not the script's.

Uses real files in a temp dir. No key, no network.

    python sections/16-coordination/src/test.py
"""
import tempfile
import threading
import time

import background
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

        # no human in the loop at all: an answer already waiting in the inbox is
        # honored; an unanswered request times out to deny (never a stall or a yes)
        team.drain("bob")
        team.send("lead", "bob", {"kind": "permission_response", "tool": "Bash", "ok": True})
        waited = mailbox.bubbling_approver(team, "bob", "lead", timeout=0.3)
        assert waited("Bash", {"command": "ls"}) is True     # the async verdict arrived
        assert waited("Bash", {"command": "ls"}) is False    # nobody answered: default deny

        # SendMessage tool: the model-facing handle that drives the channel. The
        # sender is bound to `me`, so the model only chooses the recipient and text.
        send = mailbox.message_tools(team, "alice")[0]
        assert send.name == "SendMessage"
        send.run({"to": "lead", "message": "parser done"})
        landed = team.drain("lead")[-1]
        assert landed["from"] == "alice" and landed["content"] == "parser done"

    print("16 coordination: ok")


def test_serve_mailbox():
    """The teammate's pull loop: drain the inbox, run work on the folded message,
    idle when empty. A message waiting before the loop starts is picked up; once
    the inbox drains, a bounded loop winds down (no shutdown protocol yet)."""
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", "worker"])
        team.send("lead", "worker", "run the date command")     # a task waiting in the inbox
        seen = []

        def work(prompt):
            seen.append(prompt)
            team.send("worker", "lead", "done: today")          # the teammate replies over the channel

        result = mailbox.serve_mailbox(team, "worker", work, poll=0, max_idle_polls=2)
        assert result == "idle"                                 # wound down after the inbox drained
        assert len(seen) == 1 and "run the date command" in seen[0]
        assert seen[0].startswith("<message from='lead'>")      # folded, not raw
        assert team.drain("lead")[-1]["content"] == "done: today"

    print("16 coordination: serve_mailbox ok")


def test_team_tools():
    """TeamCreate as a tool: sizing and forming the team is the lead's decision,
    not the script's. SendMessage is inert until the team exists; TeamCreate
    materializes it (creator included), and then messages deliver over the team the
    model just formed."""
    with tempfile.TemporaryDirectory() as d:
        formed = {"team": None}
        tools = {t.name: t for t in mailbox.team_tools(d, "lead", formed)}

        # SendMessage is inert until the lead forms the team
        assert formed["team"] is None
        assert "no team" in tools["SendMessage"].run({"to": "w1", "message": "hi"}).lower()

        # TeamCreate sizes and forms the roster; the creator joins automatically
        tools["TeamCreate"].run({"members": ["w1", "w2"]})      # the lead picks the size
        assert set(formed["team"].members) == {"lead", "w1", "w2"}

        # now SendMessage delivers over the team the model just formed
        tools["SendMessage"].run({"to": "w1", "message": "start"})
        assert formed["team"].drain("w1")[0]["content"] == "start"

    print("16 coordination: team tools ok")


def test_teammate_tools():
    """SpawnTeammate as a tool: calling it (standing in for the lead's tool call)
    starts a teammate loop on the section-13 runtime that pulls its inbox and
    replies. The decision to add a teammate is the tool call, not the script."""
    with tempfile.TemporaryDirectory() as d:
        team = mailbox.Team(d, ["lead", "w1"])
        runtime = background.Runtime()
        team.send("lead", "w1", "do it")                        # work waiting before the spawn

        def spawn_worker(name):
            def work(_prompt):
                team.send(name, "lead", "did it")
            return mailbox.serve_mailbox(team, name, work, max_idle_polls=5)

        spawn = {t.name: t for t in mailbox.teammate_tools(runtime, spawn_worker)}["SpawnTeammate"]
        assert spawn.is_read_only                               # spawning reads; no allow-rule needed
        spawn.run({"name": "w1"})                               # the lead's tool call starts the thread

        landed = []
        for _ in range(200):                                    # wait for the spawned teammate to reply
            landed = [m for m in team.drain("lead") if m["content"] == "did it"]
            if landed:
                break
            time.sleep(0.01)
        assert landed, "spawned teammate never replied"

    print("16 coordination: teammate tools ok")


if __name__ == "__main__":
    test()
    test_serve_mailbox()
    test_team_tools()
    test_teammate_tools()
