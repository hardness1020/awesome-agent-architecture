# deepseek-harness research notes · sections 12-15

Ticket #67, wayfinder map #63. Pinned tag: `dsh-v0.1.0-rc.7`.
All paths below are relative to the deepseek-harness repo root at that tag.
English docs only. Verdicts use the distinctive-only criterion: a real, source-verifiable
mechanism that contrasts with the section's existing columns.

---

## Section 12 · Task system

**Verdict: yes.** dsh stores work as durable session-log events, not disk task files.
Two separate records exist: a whole-list todo snapshot and one revisioned same-session goal.
Neither has dependency edges or a claim gate, which contrasts cleanly with the Claude Code column.

### Named mechanisms

- `todo_write` tool (`@deepseek-ai/dsh-tool-todo`): the model resends the entire list each call.
  Each call appends a `todo/write` session event; the current list is the latest event, last-write-wins on replay.
- `todo/write` is log-only UI state. It never enters derived model history. Web UIs render the latest event as a checklist.
- Single owner: the list belongs to the one agent session that called the tool. Non-agent callers are rejected.
- `allowParallelInProgress` config is required with no default. It switches both the tool description and validation
  between one active task and many.
- `ctx.goals` (`GoalService`, `@deepseek-ai/dsh-goal`): one durable completion objective per session.
  `GoalSnapshot` carries objective, phase, revision, and `maxGoalRounds`.
- `GoalPhase` is `active | paused | blocked | complete`. `blocked` retains a policy code plus message (`GoalBlockReason`).
- Every mutation is a durable `goal/change` session event holding a complete post-mutation snapshot or a clear tombstone.
  A strict fold replays lifecycle state from these events alone.
- Mutations are compare-and-set against an exact `GoalRef` revision. Every accepted mutation increments the revision.
- Goal activation (`armed | disarmed`) is process-local and deliberately never persisted. Resume and fork require
  a human-authorized resume through `/goal` or the model tool before automatic work restarts.
- Tools (`@deepseek-ai/dsh-tool-goal`): `create_goal`, `get_goal`, `update_goal`. Create, edit, pause, and resume
  require direct-human root authority. Complete and blocked are also allowed from inside a goal round.
- `@deepseek-ai/dsh-goal-round-driver`: at whole-agent idle it reserves round `roundsStarted + 1` and queues one
  retained `<goal_round>` user prompt with a `GoalMessageSource` attribution. Human turns never consume the round cap.
- `/goal` human command (`dsh-command-goal`) observes or mutates the goal without a model turn.

### Source anchors

- `docs/subsystems/goal.md` (GoalRef, GoalPhase, GoalSnapshot, `goal/change`, `ctx.goals` API, `goal/changed` event)
- `docs/glossary.md` (goal, goal round, goal activation definitions)
- `packages/goal/goal/src/types.ts` and `packages/goal/goal/src/domain.ts` (types; `goal/change` at domain.ts:66)
- `packages/goal/goal/src/index.ts` (GoalService, strict fold, compare-and-set)
- `packages/goal/goal-round-driver/README.md` (round contract, idle checkpoint, flush before queuing)
- `packages/goal/tool-goal/src/index.ts` with `docs/tool-catalog.md` (`create_goal`, `get_goal`, `update_goal`, authority rules)
- `packages/todo/tool-todo/README.md` and `packages/todo/tool-todo/src/index.ts` (`todo_write`, single owner, validation)
- `docs/persistence-catalog.md` (`todo/write` log-only, last-write-wins; declared at `packages/core/session/src/types.ts:299`)

### Draft column gist

- Pros: records ride the append-only session log, so replay, fork, and resume come free. Human authority gates every goal mutation.
- Cons: no dependency edges and no claim gate, so multi-worker plans need another layer. One goal per session.
- Why: the session log is the single source of truth, so task state must be events, not side files. Autonomy needs a human-held leash.
- How, task record: a whole-list todo snapshot plus one goal (objective, phase, revision, round cap). How, dependencies: none; list order only.
  How, persistence: `todo/write` and `goal/change` session events, strict fold on replay; activation is never persisted.
  How, lifecycle: goal phases active, paused, blocked, complete; compare-and-set by exact revision; a round cap bounds continuation.

### src/ update candidate

Yes. Add a goal record with a round cap and an armed/disarmed flag that gates auto-continuation, folded from an event log instead of task files.

---

## Section 13 · Background execution

**Verdict: yes.** dsh runs one kind-agnostic job registry behind three tools, with owner fencing,
first-wins settlement, and a two-lane completion delivery that the Claude Code column does not have.

### Named mechanisms

- `ctx.jobs` (`JobRegistry`, `@deepseek-ai/dsh-jobs`): abstract Service Definition.
  `LocalJobRegistry` (`@deepseek-ai/dsh-jobs-local`) is the process-local provider.
- Producers are kind-namespaced (`bash`, `subagent`, terminal sends). Ids are `<kind>-N`.
  The bash, pwsh, terminal, and subagent tools all take `run_in_background` and register with the same registry.
- `JobStatus` is `running | stopping | completed | killed | failed`. Producers hand the runtime `JobHooks`:
  a synchronous idempotent `cancel`, a `done` promise that resolves after resources release, and optional `readOutput`.
- Tools (`@deepseek-ai/dsh-tool-jobs`): `job_output(job_id, wait?, timeout_ms?)` reads the next stream delta or the
  idempotent final output, non-blocking by default; `job_list()`; `job_kill(job_id, reason?)` requests cancellation.
- Owned-job access is fenced by the owner's session id. Ids are predictable, so authorization, not secrecy, is the boundary.
- Settlement is first-wins: one terminal record, released waiters, one round of contained listener notification.
  A `reported` bit suppresses a duplicate completion notice after a kill, terminal read, wait, or teardown cancel.
- Completion delivery has two lanes. A busy owner gets the notice injected into the next-step inbox via `agent.inject()`,
  so several settlements cost one step. An idle owner is woken with a follow-up turn.
- Waking is budgeted: `maxConsecutiveWakes` (default 3) turns per owner, refilled only by a user-authored message,
  because a woken turn can start the job whose completion wakes it again. `completionDelivery: quiet` disables waking.
- `start` refuses work while no attached controller serves the owner, so a producer cannot start work the owner cannot collect or stop.
- Admission cap: `maxConcurrentJobsPerOwner` defaults to 10, counting running plus stopping records per owner.
- `outputLimitBytes` caps each complete model-facing read or notice; a bounded notice keeps the job id and the
  `job_output` collection instruction before spending bytes on label and detail.

### Source anchors

- `docs/subsystems/jobs.md` (JobStart, JobHooks, JobSnapshot, registry semantics; `JobRegistry` at `packages/jobs/jobs/src/index.ts:62`)
- `packages/jobs/jobs/src/types.ts` (JobKindMap, JobStatus, outcome shapes)
- `packages/jobs/jobs-local/src/index.ts` (LocalJobRegistry, per-owner admission)
- `packages/jobs/tool-jobs/README.md` (tool semantics, completion notices, wake budget, config table)
- `docs/tool-catalog.md` (`job_kill`, `job_list`, `job_output`; bash and subagent `run_in_background` wiring;
  `user/message via agent.inject()` for completion notices)

### Draft column gist

- Pros: one registry serves every slow kind, so shell, terminal, and subagents share collect and stop paths. Duplicate notices are suppressed.
- Cons: the wake lane spends unrequested model turns, so it needs a budget. Stream reads are single-consumer.
- Why: assumes completions must reach the model without busy-polling, and that an idle agent left unpoked never learns a job finished.
- How, off-loop primitive: any tool sets `run_in_background` and registers a kind-namespaced job; the call returns a job id.
  How, notification: a completion notice per job, first-wins settlement, a reported bit against duplicates.
  How, re-entry: inject into the next step when busy; wake a follow-up turn when idle, capped by a wake budget only human input refills.

### src/ update candidate

Yes. Adopt the two-lane re-entry: inject notifications into a busy turn, but open a new turn for an idle agent under a bounded wake budget.

---

## Section 14 · Scheduling

**Verdict: yes.** dsh schedules are session-local reminders persisted in the session log itself,
with a fixed-rate-only recurrence model and an idle-only follow-up delivery. That contrasts with both
the Claude Code column (cron plus remote triggers, separate JSON file) and the Hermes column (gateway cron, shared job store).

### Named mechanisms

- Package `@deepseek-ai/dsh-schedule` (`packages/schedule/schedule`). Doc: `docs/subsystems/schedule.md` (Session-local Schedule).
- Three record kinds: `after` (positive delay), `at` (absolute instant), `every` (fixed rate, minimum 300 seconds).
  No cron or calendar expressions exist in the protocol. Creation canonicalizes every target to RFC 3339 UTC `scheduledAt`.
- Tools: `schedule_create`, `schedule_list`, `schedule_delete`. Absolute input must carry an offset or an explicit
  `time_zone`; Schedule never reads browser, session, process, or model time-zone state.
- Persistence: the version-1 `schedule/change` session event is the only durable authority. Create stores the record,
  delete and one-shot dispatch are terminal id-only transitions, an every dispatch carries its decision time.
- Strict fold rejects unknown versions, reused ids, and transitions against inactive records.
  A fork folds only events past `SessionHeader.seedLength`, so it keeps history but drops the parent's active reminders.
- Catch-up: an overdue every record contributes only its latest due occurrence and advances directly past missed
  intervals without enumerating them. Multiple overdue every records batch one occurrence each into one follow-up turn.
- Live delivery: the process-local owner derives its earliest timer from the durable fold. Cold sessions do no work;
  reopening a session reconstructs timers. Due work waits for the agent to become fully idle, claims the maintenance
  phase, queues one `followup()` turn, then appends the dispatch change. It never calls `steer()` and never interrupts a turn.
- Delivery mode is `session-local`: the original session must be live. There is no external channel or cold-session scheduler.
- The boundary is at-least-once: a crash after queue admission but before the durable dispatch write can repeat a reminder.
- Stable error codes include `persistence_uncertain`, `not_future`, `frequency_too_high`, and `corrupt_schedule_log`.

### Source anchors

- `docs/subsystems/schedule.md` (record shapes, catch-up, replay, live delivery, error codes)
- `packages/schedule/schedule/src/types.ts` (`schedule/change` declared at types.ts:219 per `docs/persistence-catalog.md`)
- `packages/schedule/schedule/src/runtime.ts` and `packages/schedule/schedule/src/persistence.ts` (timer owner, fold)
- `packages/schedule/schedule/src/tools.ts` with `docs/tool-catalog.md` (`schedule_create`, `schedule_list`, `schedule_delete`)
- `packages/schedule/schedule/tests/jsonl-restart.spec.ts` and `tests/recurrence.spec.ts` (restart and recurrence behavior)

### Draft column gist

- Pros: reminders replay with the session, so restart needs no separate store. Missed fires collapse to one turn instead of a backlog.
- Cons: fixed-rate only, no cron calendar. Delivery needs the original session live, so nothing fires cold.
- Why: treats a reminder as conversation state, so the session log is its only durable authority and delivery is an ordinary later turn.
- How, trigger: after-delay, absolute-at, or fixed-rate every with a five-minute floor; timers derive from the durable fold.
  How, durability: `schedule/change` events in the owning session log, strict fold, forks drop active reminders.
  How, wakeup: due work waits for full idle and queues one follow-up turn; overdue recurrences batch; at-least-once, never exactly-once.

### src/ update candidate

Yes. Adopt the catch-up rule: on reload, a recurring task fires once for its latest due occurrence and re-arms past the missed ones.

---

## Section 15 · Worktree isolation

**Verdict: no. Hard verdict: dsh has no analogue to worktree isolation at this tag.**
No mechanism gives parallel agents separate copies or checkouts of a directory.
Every `worktree` mention in the repo is contributor workflow (git hooks, build hygiene, review automation), not a harness mechanism.

### What exists instead (and why it does not qualify)

- `ctx.workspaceRegistry` (`@deepseek-ai/dsh-workspace`): a workspace is a persistent host-side record of a directory,
  a generated uuid over a canonical path with an ordered account of sessions. It groups sessions for the GUI.
  The doc states it is invisible to models: no tools, no prompt text, no session events. It is bookkeeping, not isolation.
- Path identity: `realpathNormalize` (`fs.realpath`) is the one uniqueness canon; uniqueness is string equality of
  canonical paths, and attach-time session cwd checks use the same canon. Deleting a workspace never touches files or logs.
- Subagents inherit the parent's execution world: the required `parent` supplies the session cwd, so parallel
  subagents write into the same directory. Nothing serializes conflicting writes between them.
- Ralph loop rounds deliberately share state: each round opens a fresh child, and the shared workspace is the
  long-term memory that crosses rounds. Sharing is the design, not an accident.
- `ctx.sandbox` (`@deepseek-ai/dsh-sandbox`) is file-effect confinement (`read-only`, `workspace-write`,
  `danger-full-access`). It bounds where a process may write; it does not give parallel work separate copies.
- The e2b family (`packages/e2b`) places one filesystem and process execution world in a remote Linux sandbox
  per composition. It relocates the shared world; it does not split it per task.

### Source anchors

- `docs/subsystems/workspace.md` (workspace entity, `ctx.workspaceRegistry`, "invisible to models" scope statement)
- `packages/workspace/workspace/src/paths.ts` (`realpathNormalize`) and `packages/workspace/workspace/src/index.ts` (registry, at index.ts:92)
- `docs/subsystems/subagent.md` (required `parent` supplies the session cwd)
- `docs/tool-catalog.md` (Ralph tool text: "the shared workspace is long-term memory")
- `docs/subsystems/sandbox.md` (`SandboxMode`, file-effect policy only)
- `packages/e2b/README.md` (one execution world per composition)
- `docs/development.md` and `docs/cookbook/maintaining-dsh-code-review.md` (worktree mentions are contributor process only)

### Draft column gist

Not applicable: no dsh column under the distinctive-only criterion. If the section ever compares
non-isolating designs, the one-line contrast is: dsh shares one canonical directory per workspace record,
confines writes with a sandbox mode, and accepts shared-directory races between parallel agents.

### src/ update candidate

No. There is no dsh isolation mechanism for the runnable to adopt.

---

## Sources

- deepseek-harness at tag `dsh-v0.1.0-rc.7`: `docs/subsystems/` (goal, jobs, schedule, workspace, sandbox, subagent, session),
  `docs/tool-catalog.md`, `docs/persistence-catalog.md`, `docs/glossary.md`, `docs/architecture.md`,
  and the package sources cited per section above.
