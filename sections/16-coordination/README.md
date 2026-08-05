# 16 · Coordination

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> A lead forms a team sized to the task, spawns teammates on their own threads, and they talk over a shared inbox.

One agent has one context window and one active line of work. Large jobs often need several agents working at once.

A subagent can handle a focused task, but a one-shot subagent is hard to steer after it starts.

A team is not free. Every extra agent costs tokens, and two agents can disagree about the same file.
So the first decision is the shape: how many agents, whether they share one context, and who directs whom.

Coordinated agents need a way to spawn each other, stable names, inboxes to talk, and a way to send permission requests back to a human.

Coordination must:

1. Give agents stable addresses.
2. Let the lead size and form the team for the task.
3. Let the lead spawn each teammate onto its own thread.
4. Let each teammate pull its inbox and act without the script driving it.
5. Bubble gated actions to a human approver.

Without this layer, large work either stays serial or splits into workers that cannot collaborate.

---

## Mechanism

![Mechanism diagram](assets/16-coordination.png)

Each agent owns an inbox. Sending a message means writing to the recipient's inbox. Delivery happens when the recipient drains its inbox.

The team's size and names are decided at run time by the lead's model, not hard-coded in the script.
The lead calls `TeamCreate` to form the team for the task, then spawns each member.

The lead does not hand-start teammates. It calls `SpawnTeammate`, and the harness runs the teammate's loop on a background thread (section 13).
The teammate then pulls its own inbox and acts, so the script drives no one.

There is no central broker in the demo. There is a shared convention for names, inbox paths, and message shape.

- Each agent owns one inbox.
- A message has a sender, recipient, and content.
- The lead calls `TeamCreate` to size and form the roster; `SpawnTeammate` then starts each member.
- The lead spawns a teammate with `SpawnTeammate`; that teammate runs on its own thread.
- `to="*"` broadcasts to every teammate except the sender.
- Senders write and return. They do not block waiting for a reply.
- A teammate pulls its inbox each poll and folds new messages into its next turn.
- Permission requests use the same channel.

### Choosing a team shape

A second agent helps only when it brings information the first one lacked: a test result, a screenshot, a lookup, a check against a real system.
An agent that rereads the same text and votes adds tokens, not information.
Under equal thinking token budgets, a single agent matched multi-agent systems on the tasks Tran and Kiela measured.
Anthropic reports its research team spending roughly fifteen times the tokens of a single chat turn. The team has to buy something with that spend.

The next choice is whether contexts are shared:

- **Shared.** The next agent inherits the whole trajectory. Nothing has to be packed, and no fact is lost in transit. One agent runs at a time, and the window fills for everyone.
- **Isolated.** Each agent keeps its own window and states what it needs. Agents run in parallel, and one agent's confusion stays local. Every handoff has to be written out.

Share when the subtasks are few, the combined history still fits one window with room to spare, and the work is serial anyway.
Isolate when subtasks are many, when the history would not fit, when the work parallelizes, or when a bad turn must not spread.
This repo isolates throughout: a subagent starts fresh (section 6), and a teammate owns an inbox.

Topology is the third choice. It only applies to isolated agents:

- **Peer.** Agents of equal standing message each other. Fits review and cross-checking.
- **Manager.** One lead splits the work, assigns it, and merges the results. Children return summaries, not trajectories.
- **Decentralized.** No lead. Each agent hands the work to whichever agent it thinks fits next.

This section builds a manager: the lead forms the roster, spawns, and delegates.
The lead plans for everyone, so the plan bounds the run and no worker recovers a bad split. Put the strongest model on the lead and cheaper models on the workers.

Decentralized designs differ in how a handoff finds its target.
MetaGPT publishes each message to a pool and roles subscribe to the types they handle, so a sender never names a receiver.
AutoGen's group chat keeps one shared transcript and a central selector picks the next speaker, which can livelock when it keeps picking the same pair.
OpenAI Swarm makes the handoff a tool call and caps the hops, so a handoff cycle ends.

### New: forming the team

`TeamCreate` is a tool the lead calls to size and form the roster. It fills a one-slot holder the harness reads back when it spawns each member:

```python
def team_tools(root, me, formed):                      # src/mailbox.py
    def create(a):
        members = list(dict.fromkeys([me, *a["members"]]))   # the lead joins its own team
        formed["team"] = Team(root, members)                 # the tool call sizes and forms the team
        return f"team created: {', '.join(members)}"
    ...                                                # SendMessage stays inert until the team exists
```

- The script fixes neither the size nor the names; the lead picks both from the task.
- `SendMessage` is inert until `TeamCreate` runs, so the lead forms the team before it can talk to it.
- `formed` is a one-slot holder (ponytail: an in-process stand-in for a team registry; back it with a roster file to let a teammate in another process join).

### New: spawning a teammate

`SpawnTeammate` is a tool the lead's model calls. The harness starts the teammate's loop on the section-13 runtime, on its own thread:

```python
def teammate_tools(runtime, spawn_worker):             # src/mailbox.py
    def spawn(a):
        runtime.start(lambda: spawn_worker(a["name"]))  # section-13 thread runs the teammate's loop
        return f"spawned teammate {a['name']}; it runs on its own thread and pulls its own work"
    return [Tool("SpawnTeammate", spawn, is_read_only=True, ...)]
```

The teammate's loop is `serve_mailbox`: pull the inbox, act, repeat. It runs on the spawned thread, so the teammate reacts on its own, not on a script:

```python
def serve_mailbox(team, me, work, *, poll=0.05, max_idle_polls=None):   # src/mailbox.py
    while True:
        chat = [m for m in team.drain(me) if isinstance(m["content"], str)]
        if chat:                                        # a message to act on
            folded = "\n".join(f"<message from={m['from']!r}>{m['content']}</message>" for m in chat)
            work(folded)                                # one inner loop (section 1) on the message
            continue
        time.sleep(poll)                                # empty: poll again
```

- `spawn_worker(name)` is the app's thunk; it runs one `serve_mailbox` loop for that teammate.
- The teammate consumes messages as it drains, so a message is delivered once.
- There is no graceful stop yet. The thread is a daemon that dies with the process. Section 17 adds the shutdown handshake.
- `max_idle_polls` bounds the idle wait so a demo or test ends; a real teammate polls until the process stops.

### The inbox and the permission channel

Isolated agents talk in one of two paradigms, the same two that processes use.
Shared memory: everyone reads and writes one place and sees the same state. Message passing: a sender addresses a copy to a receiver, and the two hold nothing in common.
Three channels cover most designs. Tool-call arguments are one shot with no reply path. A shared filesystem is durable but needs locks.
A message bus is addressed and ordered, and durable only if it persists.
Inboxes here are message passing. Team memory (section 9) and the task board (section 18) are shared memory.
A team usually wants both: messages to direct work, shared memory for facts that outlive a message.

`mailbox.py` implements a `Team` of named inboxes:

```python
def send(self, frm, to, content):                      # src/mailbox.py
    targets = [m for m in self.members if m != frm] if to == "*" else [self._check(to)]
    with self._lock():                                 # serialize concurrent senders
        for t in targets:
            inbox = self._read(t)
            inbox.append({"from": frm, "to": t, "content": content})
            self._path(t).write_text(json.dumps(inbox))
```

- `_check` rejects unknown names before they become paths.
- The lock serializes read-modify-write, so concurrent senders do not drop messages.
- `drain` reads and clears one inbox.

Permission bubbling is an approver implementation. It moves a gated call to a human over the same channel:

```python
def bubbling_approver(team, me, lead, human=None, timeout=0.0, poll=0.05):
    def approve(name, args):                            # approver for an agent with no human UI
        team.send(me, lead, {"kind": "permission_request", "tool": name, "args": args})
        if human is not None:                           # the lead routes it to its approval UI
            team.send(lead, me, {"kind": "permission_response", "tool": name, "ok": human(name, args)})
        deadline = time.time() + timeout
        while True:
            resp = [m["content"] for m in team.drain(me)
                    if isinstance(m["content"], dict) and m["content"].get("kind") == "permission_response"]
            if resp:
                return bool(resp[-1]["ok"])
            if time.time() >= deadline:
                return False                            # nobody answered in time: default deny
            time.sleep(poll)
    return approve
```

1. A teammate hits a gated tool call, but its own loop has no human at the keyboard.
2. The approver sends a `permission_request` to the lead's inbox.
3. The lead routes it to its approval UI (the `human` callback here).
4. The verdict returns as a `permission_response` in the teammate's inbox.
5. The teammate reads that response and returns allow or deny to the gate.

The gate still calls `approver(name, args)` and does not change. The answer arrives as an inbox message, not a direct call, so escalation reuses the same channel.

Without `human`, the answer must come from elsewhere (a lead on another thread, a person on a chat platform).
The approver polls its inbox up to `timeout` and then denies: an unanswered permission is a no, never a stall or a yes.
This mirrors Hermes' clarify gateway, where `wait_for_response` blocks the agent thread until a chat adapter answers or the timeout fires.

### Where team state lives

Agents address each other by name and address state by path. The book splits the tree into four regions, each with its own rule:

- **Private scratchpad.** One agent writes and nobody else reads. Drafts and intermediate output. No coordination needed.
- **Shared workspace.** Any teammate reads and writes: the repo, the task board, team memory. Conflicts live here, so it needs locks or separate worktrees (section 15).
- **External mounts.** Data the team did not produce, such as a checkout or a dataset. A write here is an effect on the outside world.
- **Read-only built-ins.** Skills, prompts, tool definitions (sections 7 and 2). Fixed for the run, so every agent sees the same copy.

Misplacing state shows up as a coordination bug. Two agents editing one file is a shared-workspace problem, and a fact repeated across three messages belonged in team memory.

### What a handoff carries

A teammate cannot see the lead's chat, so "fix the failing test" is not actionable. A handoff packet carries three things:

1. The task, with acceptance criteria the receiver can check by itself.
2. The facts already confirmed and the constraints that hold, so the receiver neither rediscovers nor breaks them.
3. Paths to the artifacts: files, logs, branches.

The raw trajectory stays out. It is long, it carries dead ends, and it makes the receiver re-read the sender's mistakes.

Shared-context handoff is the alternative. One agent transfers control and the whole history rides along, so nothing gets packed and nothing is dropped in transit.
The book shows this with a role-to-role transfer tool. That is the book's own experiment, so treat it as a single source.
Control is a baton there: one agent holds it, so nothing runs in parallel. Packets cost writing effort and buy parallelism.

### How it integrates

The demo runs one main agent. The lead takes one step, and the teammate runs itself:

```python
def spawn_worker(name, formed, model):                 # src/demo.py, module level
    team = formed["team"]                              # whatever the lead formed with TeamCreate
    ...                                                 # build the teammate's tools
    return mailbox.serve_mailbox(team, name, work)      # the teammate pulls its own inbox

run_turn([...goal...], model, lead_reg, session)        # the one agent call in demo(): the lead
```

- The only scripted input is the lead's goal. The lead sizes the team with `TeamCreate`, spawns each with `SpawnTeammate`, and delegates with `SendMessage`.
- `demo()` runs one `run_turn`, the lead's. The teammate's own `run_turn` lives in `spawn_worker`, reached only through the spawn tool.
- Each teammate runs `serve_mailbox` on a section-13 thread: it pulls its inbox, works, and replies. The number of replies is the lead's choice; the main process only waits.
- `loop.py` stays generic. Folding and the pull loop are coordination, done in this wrapper, not inside `run_turn`.
- The permission gate does not change; a gated call still bubbles to the lead.

> **Next:** A teammate here is a daemon with no graceful stop, and it only reacts to messages.
> Section 17 adds the shutdown handshake so the lead can end a teammate cleanly.
> Section 18 adds a shared task board, so an idle teammate claims its own work instead of waiting to be messaged.

---

## Per system

How one design spawns cooperating agents and spreads work across them.

| | Claude Code | Hermes Agent |
| --- | --- | --- |
| **Pros** | Peers talk directly. File inboxes are durable and cross processes or machines. | Children can be paused, checked, and interrupted from any connected surface. |
| **Cons** | File inboxes add polling and lock cost. In-memory inboxes die with the process. | No peer inboxes, so children cannot collaborate. A clarify blocks its thread. |
| **Why** | Teammates are peers that need inboxes to talk and a route to a human approver. | Coordination stays parent to child. A human on chat answers escalations. |
| **How: teammates** | In-process or remote. Each runs its own loop, folding messages between turns. | Delegated children on threads. A pause flag stops new spawns mid-run. |
| **How: channel** | SendMessage writes to memory or locked file inboxes and can broadcast. | Completion queue plus gateway RPCs. The parent folds results in when idle. |
| **How: shared memory** | Team task list and a team memory directory. | Shared session DB. Lineage markers record who spawned whom, for cascade cleanup. |
| **How: permission bubbling** | Remote requests become local approval prompts. | Clarify requests route to the user's chat. Children get auto-deny or auto-approve, logged. |

---

## Failure modes

- **Lost message race.** Two senders write one inbox at once. Lock read-modify-write.
- **Peer deadlock.** Agents wait on each other. Queue messages and drain between turns instead of blocking sends.
- **Permission stalls.** A teammate has no human UI. Bubble the request to the lead.
- **Spawn before create.** The lead spawns or messages before `TeamCreate`, so there is no roster. Keep both inert until the team exists.
- **Orphaned teammate.** A spawned teammate keeps polling after its work is done. Bound the idle wait, or stop it with the section-17 handshake.
- **Vague cross-agent message.** A teammate cannot see the lead's chat. Send a packet: task, acceptance criteria, confirmed facts, artifact paths.
- **Chat used as memory.** Durable shared facts belong in team memory.
- **Byzantine teammate.** A failed agent does not crash. It returns a confident wrong answer, so retries and votes over the same evidence miss it.
  Only a check against something outside the model catches it.
- **Lost update on a shared file.** Two agents read one file, both write, and the first write is gone. Lock the write, or store a version and retry when it does not match.
- **Semantic conflict.** Both writes land cleanly and the result is still wrong: one agent renamed what the other called.
  Split work so two agents never own one concept, or merge at one point.
- **Error cascade.** A wrong fact from an upstream agent gets repeated downstream and starts reading as confirmed.
  A reviewer that sees only conclusions finds them consistent. Review against the raw evidence, by an agent that did not produce it.

---

## Runnable

[`src/`](src/) carries 15 forward and adds:

- [`mailbox.py`](src/mailbox.py): named inboxes with locking, folding, the `serve_mailbox` loop, bubbling with timeout and default deny, and the team tools.
- [`test.py`](src/test.py): checks addressing, broadcast, concurrent send, folding, bubbling (inline, async, and timeout-deny), the mailbox loop, and the team tools.
- [`demo.py`](src/demo.py): the lead takes one step (`TeamCreate`, `SpawnTeammate`, `SendMessage`); each teammate pulls its inbox, runs a gated shell task, and reports back.

The loop and subagent path are unchanged. Coordination wraps a turn by spawning teammates, draining inboxes, and passing an approver.

```bash
python sections/16-coordination/src/test.py         # offline checks, no key
uv run python sections/16-coordination/src/demo.py  # live demo, needs a key
```

---

## Sources

- [Claude Code tools and inboxes](https://github.com/yasasbanukaofficial/claude-code):
  `tools/SendMessageTool/`, `tools/TeamCreateTool/`, `utils/mailbox.ts`, `utils/teammateMailbox.ts`.
- [Claude Code teammates](https://github.com/yasasbanukaofficial/claude-code):
  `tasks/InProcessTeammateTask/`, `tasks/RemoteAgentTask/`, `remote/remotePermissionBridge.ts`, `memdir/teamMemPaths.ts`.
- [Hermes Agent source](https://github.com/NousResearch/hermes-agent): `tools/delegate_tool.py`, `tools/async_delegation.py`, `tools/clarify_gateway.py`, `tools/interrupt.py`.
- [learn-claude-code · s15_agent_teams](https://github.com/shareAI-lab/learn-claude-code): section framing.
- [ai-agent-book](https://github.com/bojieli/ai-agent-book): `book/chapter10.md` (多 Agent 协作), Chinese original canonical.
  Context sharing, topology taxonomy, filesystem regions, handoff packets. The role-transfer demo is the author's own experiment.
- Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* ([arXiv:2503.13657](https://arxiv.org/abs/2503.13657)): the MAST taxonomy and the Byzantine framing.
- Tran, Kiela, *Single-Agent LLMs Outperform Multi-Agent Systems Under Equal Thinking Token Budgets* ([arXiv:2604.02460](https://arxiv.org/abs/2604.02460)).
- Erdogan et al., *Plan-and-Act* ([arXiv:2503.09572](https://arxiv.org/abs/2503.09572)): planner quality bounds the run.
- Anthropic, [*How we built our multi-agent research system*](https://www.anthropic.com/engineering/multi-agent-research-system): token cost of a research team.
- [MetaGPT](https://arxiv.org/abs/2308.00352), [AutoGen](https://arxiv.org/abs/2308.08155), [OpenAI Swarm](https://github.com/openai/swarm): decentralized routing and handoff caps.
