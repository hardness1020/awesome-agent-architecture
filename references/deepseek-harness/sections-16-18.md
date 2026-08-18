# deepseek-harness research notes: sections 16 to 18

Pinned tag: `dsh-v0.1.0-rc.7`. All paths below are relative to the deepseek-harness repo root.
Judged against the existing columns in `sections/16-coordination/README.md` (Claude Code, Hermes Agent),
`sections/17-protocols/README.md` (Claude Code), and `sections/18-autonomy/README.md` (Claude Code).

---

## Section 16 · Coordination

### Verdict: yes

A dsh column is distinctive. The existing columns coordinate through peer inboxes (Claude Code) or a
completion queue with gateway RPCs (Hermes). dsh has no peer channel at all. Coordination is strictly
hierarchical: a parent fans out children through a provider registry, a model-written orchestration
script, or resident continuable children, and every message to a child is a FIFO turn in that child's
own Agent inbox. Children answer only through an explicit `report` tool. All of this is source-verified.

### Named mechanisms

- `ctx.workflowEngine` (package `dsh-workflow`): a capability seam for model-written JS orchestration
  scripts. The engine is `dsh-workflow-worker-thread` (one `node:worker_threads` worker per run); the
  model-facing consumer is the `workflow` tool (`dsh-tool-workflow`).
- Script hooks: `agent()`, `parallel()`, `pipeline()`, `phase()`, `log()`. `agent()` starts one
  host-side subagent and returns final text or a structured value; a failed child yields `null`.
- `WorkflowStartRequest.maxTotalAgents`: per-run total-child ceiling. The worker enforces
  `WorkerLimits`: `maxTotalAgents` (default 1000, a runaway-loop backstop that throws `AGENT_CAP`),
  `maxConcurrentAgents` (0 resolves from CPU parallelism), `maxItemsPerCall` (4096), `syncTimeoutMs`.
  A per-run cap may lower but never raise the deployment ceiling.
- `WorkflowStartRequest.parent` is required: every child a script starts is attributed to that live
  Agent, and cwd, lineage, and depth pass through the subagent seam. The script cannot observe or
  replace the provider or cap policy.
- Observe-only events: `workflow/start`, `workflow/phase`, `workflow/log`, `workflow/agent-start`,
  `workflow/agent-end` (paired by `agent.seq`), `workflow/end`; payloads are data snapshots, cloned
  per listener.
- `ctx.subagents` (package `dsh-subagent`): a named provider registry. Providers: `spawn`, `fork`
  (in-process), `acp`, `codex`, `claude-code`, `dsh-sdk` (out-of-process).
- Parent lineage and depth: the child session header records `parentSession`; delegation depth is
  `delegationDepthOf(parent) + 1`, persisted as `SessionHeader.delegationDepth`, monotone on cold
  resume, with an optional absolute `maxDepth` cap rejected at start when unsupported.
- Continuable children: one durable child Session with at most one process-local Activation. The
  Agent inbox is the only turn FIFO. `followup()` routes on residency: `running` enqueues, `waiting`
  wakes, no Activation cold-resumes. Only the direct parent recorded in `parentSession` may deliver.
- Control tools (`dsh-tool-subagent-control`): `send_message` (becomes the child's next FIFO turn,
  returns no reply), `interrupt_agent` (ancestor authority, stops only the current turn, `keepInbox`
  parks queued work), `list_agents` (`children` or `descendants` scope; `running`/`idle`/`ready`).
- Return channel (`dsh-tool-subagent-report`): a child-scoped `report` tool over
  `ctx.subagents.reportFrom()`. The child is the authority credential; the recipient is always its
  durable parent. Delivery policy is `wakeup` (`parent.followup()`, one later parent turn) or `quiet`
  (`parent.inject()`, context only). When an Activation settles, the manager itself delivers one
  `subagent-settled` notice to the parent, typed apart from child-authored reports.
- Ralph (`dsh-tool-ralph`): a fixed foreground workflow that runs one immutable objective through a
  sequence of fresh children with structured `continue | complete | blocked` handoffs; the shared
  workspace is the long-term memory, and no conversation is seeded.

### Source anchors

- Workflow seam, caps, parent attribution: `docs/subsystems/workflow.md`.
- Cap enforcement and hooks: `packages/workflow/workflow-worker-thread/src/runtime.ts` (AGENT_CAP),
  `packages/workflow/workflow-worker-thread/src/types.ts` (`WorkerLimits`),
  `packages/workflow/workflow/src/runtime-types.ts` (`WorkflowStartRequest.maxTotalAgents`).
- Engine defaults (provider `spawn`, `maxTotalAgents` 1000, `maxConcurrentAgents` 0 = CPU):
  `packages/workflow/workflow-worker-thread/README.md`.
- Provider registry, lineage, depth, Activations, followup routing, interrupt, report, settled
  notice: `docs/subsystems/subagent.md`.
- Depth computation: `packages/subagent/subagent/src/child-agent.ts`,
  `packages/subagent/subagent/src/depth.ts`.
- Control tools: `packages/subagent/tool-subagent-control/README.md`.
- Report tool and delivery policy: `packages/subagent/tool-subagent-report/README.md`.
- Inbox admission vocabulary (`send`, `followup`, `steer`, `inject`, `next-turn`/`next-step`,
  claim batches): `docs/subsystems/core.md`.
- Ralph rounds and handoffs: `packages/workflow/tool-ralph/README.md`.

### Draft column gist

- Pros: a script fans out hundreds of children under hard caps. Every message has one FIFO order.
- Cons: children cannot talk to each other. A send returns no reply, so the parent waits on reports.
- Why: coordination is ownership. Every child has exactly one parent, so authority and cleanup
  follow lineage, and a runaway loop hits an engine cap instead of the API bill.
- How: teammates: a model-written workflow script spawns one-shot children in a worker thread;
  continuable children stay resident; six provider transports, in-process and out-of-process.
- How: channel: parent to child only. `send_message` becomes the child's next inbox turn; the child
  answers through its `report` tool. No peer inboxes, no broadcast.
- How: shared memory: the shared workspace under the parent's cwd; the fork provider seeds a child
  with the parent's completed-turn prefix.
- How: permission bubbling: an `approval/request` waterfall answers per scope; ACP children
  auto-answer by configured policy; unanswered means `unavailable`, which fails closed.

### src/ update candidate: yes

Add a `maxTotalAgents`-style spawn backstop to section 16's team tools: `SpawnTeammate` counts
spawns per run and refuses past a cap, mirroring dsh's runaway-loop `AGENT_CAP`.

---

## Section 17 · Protocols

### Verdict: yes

A dsh column is distinctive. The existing Claude Code column is a private typed message union with
`request_id` correlation inside one team. dsh instead speaks a public standard across a process and
trust boundary: it is both an ACP (Agent Client Protocol) server and an ACP client, correlates by
branded session id plus a one-in-flight prompt slot, and stops children with a graded teardown
ladder instead of a confirm handshake.

### Named mechanisms

- ACP server (`packages/acp/acp`, plugin `dsh-acp`): automation-only Agent Client Protocol over
  JSON-RPC stdio. Methods: `initialize` (capability negotiation), `session/new` (fresh agent with an
  absolute cwd), `session/prompt` (one in-flight request per session; settles `end_turn` or
  `cancelled`), `session/cancel`, `session/update` (`agent_message_chunk` per committed block),
  `session/request_permission` (one-shot allow/reject choices a client may answer automatically).
  Committed-message output only: uncommitted deltas, reasoning, and tool activity stay off the wire.
- Correlation: the bridge keys records by branded session id and checks exact agent identity before
  routing events or permission requests; each session has its own prompt slot and disposer. Every
  prompt response carries a `stopReason`.
- ACP client (`packages/subagent/subagent-acp`, provider name `acp`): spawns a fresh subprocess per
  child and drives it as an ACP client (`spawn`, then `initialize`, then `newSession` before the
  start fulfills). It advertises no start-time capabilities because it cannot enforce the remote
  child's depth, filter, persona, or schema, and reports `inheritsParentContext: false`.
- Permission bridging by policy: the client's `permission` config auto-answers remote
  `session/request_permission` by rejecting (default) or by choosing the first allow option.
- Shutdown ladder: `dispose()` requests ACP cancellation, closes stdin and waits
  `disposeEofGraceMs` (6000ms) for cooperative quiescence, then SIGTERM, `disposeGraceMs` (3000ms),
  SIGKILL, and awaits whole-tree exit proof. Cooperation first, kill as the timed fallback.
- Internal stop: `ctx.subagents.interrupt()` is fire-and-return under ancestor authority with
  `keepInbox`; unclaimed inbox work parks and a later waking send resumes the FIFO queue.
- Plan gate: `exit_plan_mode` (`dsh-plan-mode`) presents a complete markdown plan through the
  user-questions seam. Approval returns `{ approved: true }` and records a pending exit; a
  keep-planning verdict is a failed tool call carrying the user's feedback, so the model revises.
- Session fork: `ctx.sessions.fork(source, boundary?, childSessionId?)` selects events through an
  inclusive boundary seq, requires the prefix to end outside an open turn (rejects instead of
  clipping), and creates a child with deep-cloned seed events plus `parentSession`, `seedLength`,
  and inherited cwd. The fork provider clips to the parent's completed-turn prefix at tool time.

### Source anchors

- ACP server contract, prompt slot, stopReason settlement, lifecycle teardown:
  `packages/acp/acp/README.md`.
- ACP group framing (server here, client in subagent): `packages/acp/README.md`.
- ACP client start sequence, permission policy, dispose ladder and graces:
  `packages/subagent/subagent-acp/README.md`.
- Interrupt semantics (`keepInbox`, ancestor authority): `docs/subsystems/subagent.md`.
- Plan gate flow and keep-planning-as-failed-call: `docs/subsystems/plan.md`.
- Fork API and open-turn rejection: `docs/subsystems/session.md` (Live-session fork API).
- Approval outcomes consumed fail-closed: `docs/subsystems/approval.md`.

### Draft column gist

- Pros: any ACP client or server interoperates; no private wire format. A stuck child cannot wedge
  the parent because every stop tier is time-bounded.
- Cons: committed-only output hides live progress. Fresh sessions only: no resume or fork over the
  wire, and a remote child's capabilities cannot be enforced.
- Why: the other side is a separate process you may not own, so the contract is a public protocol
  plus process-level teardown, not a shared inbox with trusted ids.
- How: message shape: JSON-RPC ACP methods keyed by branded session id; one in-flight prompt per
  session; every prompt response carries a `stopReason`.
- How: plan approval: `exit_plan_mode` sends the plan through the user-questions seam; rejection
  returns as a failed call carrying feedback, so the loop revises and re-presents.
- How: shutdown: ACP cancel, then stdin EOF plus grace, then SIGTERM plus grace, then SIGKILL, with
  whole-tree exit proof. Internal interrupts keep the inbox parked for a later resume.

### src/ update candidate: yes

Implement section 17's two-tier stop in `src/`: `StopTeammate` waits for the confirm up to a
deadline, then hard-stops the thread, mirroring dsh's graded EOF/SIGTERM/SIGKILL ladder.

---

## Section 18 · Autonomy

### Verdict: yes

The evidence supports a column. The existing Claude Code column is board autonomy: idle workers
claim tasks off a shared board. dsh has no shared task board; its autonomy is self-continuation on
one session plus explicit autonomy levels. Three source-verified mechanisms carry the column: the
headless one-shot runner, named permission presets bundling sandbox mode with approval policy, and
the goal-round driver that re-prompts an idle agent until its durable goal ends or the cap runs out.
The ticket's initial scan found no explicit autonomy levels; the preset table is exactly that, so
the earlier finding is superseded. Borderline only in that the three mechanisms are three packages,
not one subsystem; the column should name all three.

### Named mechanisms

- Headless one-shot runner (`packages/bundle/headless`, plugin `headless-runner`):
  `dsh --profile headless "task"` creates one fresh persisted Agent, submits the task as an ordinary
  user message, waits for quiescence, prints the last non-empty assistant text, and exits 0 only
  when the final `turn/end` completed. No listening port, no interactive follow-up.
- Approval policy (`dsh-user-approval`, `ctx.approval`): per-session `ApprovalPolicy = 'ask' | 'never'`.
  `never` deterministically rejects every ask before any answerer runs (the strict headless stance);
  outcomes are closed and fail-closed (`allowed-once` is the only grant; missing answerers yield
  `unavailable`).
- Autonomy levels (`dsh-permission-presets`, `ctx.permissionPresets`): a named preset bundles one
  sandbox mode with one approval policy. The base bundle ships `read-only` (read-only + ask),
  `workspace-write` (workspace-write + ask), `danger-full-access` (danger-full-access + never),
  defaulted from `DSH_PERMISSION_MODE`. Switching appends a log-only `permission/preset` event and
  writes each knob through its own setter; unmatched knob states derive as `custom`.
- Goal domain (`dsh-goal`, `ctx.goals`): a durable same-session goal with phases
  `active | paused | blocked | complete`, a revision counter, and a `maxGoalRounds` cap. Activation
  (may the driver start another round) is process-local and never persisted.
- Goal-round driver (`dsh-goal-round-driver`): at whole-agent idle, an active armed goal with
  remaining capacity reserves round `roundsStarted + 1` against the exact `{ goalId, revision }` and
  queues one `<goal_round>` prompt. A stale reservation does not consume the number. Human messages
  never consume the cap, and automatic work yields to human input until the agent is idle again.
  Cancellation pauses or disarms the goal so it cannot auto-restart.
- Bounded fresh-agent iteration (`dsh-tool-ralph`): `maxRounds` (default and ceiling 256) is carried
  as the engine's `maxTotalAgents`, so the loop and the runaway backstop share one number; terminal
  results are `complete`, `blocked`, or `budget-limited`.

### Source anchors

- One-shot runner and exit codes: `packages/bundle/headless/README.md`; CLI surface
  (`dsh --profile headless "job"`): `apps/cli/README.md`.
- Approval policy and fail-closed outcomes: `docs/subsystems/approval.md`.
- Preset table, `custom` derivation, `permission/preset` event: `docs/subsystems/permission-presets.md`;
  shipped three-preset table and `DSH_PERMISSION_MODE` default: `packages/bundle/base/cordis.patch.yml`.
- Goal phases, rounds, revisions: `docs/subsystems/goal.md`.
- Round reservation, idle checkpoint, yield-to-human, disarm-on-cancel:
  `packages/goal/goal-round-driver/README.md`.
- Ralph round cap as `maxTotalAgents`: `packages/workflow/tool-ralph/README.md`.

### Draft column gist

- Pros: unattended runs are deterministic: `never` rejects every ask, and each level is one named
  preset. Continuation is durable, so a resumed session knows its goal and remaining rounds.
- Cons: one agent continues one goal; no idle worker pool drains a shared board. The model itself
  judges completion, with no independent evaluator.
- Why: autonomy is a budgeted permission level, not a mode. What the run may touch and how it ends
  are decided up front, and every autonomous round is charged against a durable cap.
- How: idle behavior: at whole-agent idle the driver checkpoints, then reserves the next goal round
  and queues one `<goal_round>` prompt; human input makes automatic work yield.
- How: work claim: compare-and-set on `{ goalId, revision }` for round `roundsStarted + 1`; stale
  reservations do not consume the cap, and only an admitted message advances it.
- How: self-organization: no board. The agent continues its own durable goal; fan-out goes through
  the workflow engine or Ralph, both capped by `maxTotalAgents`.

### src/ update candidate: yes

Add a per-goal round cap to section 18's outer loop: the idle poll stops claiming after N
autonomous rounds and yields whenever a human or lead message is pending, mirroring the goal-round
driver's cap and yield rules.
