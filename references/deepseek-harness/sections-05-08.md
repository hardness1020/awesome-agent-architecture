# deepseek-harness research notes · sections 5 to 8

Pinned tag: `dsh-v0.1.0-rc.7`. All paths below are relative to the deepseek-harness repo root.
Scope: distinctive-only verdicts for a dsh column in sections 5 (planning and todos), 6 (subagents), 7 (skills), 8 (context management).

---

## Section 5 · Planning and todos

**Verdict: yes.** The todo tool is close to Claude Code's `TodoWrite` (whole-list replace, three statuses),
but the storage and the plan mode contrast cleanly. dsh stores todos and plan state as durable session-log
events recovered by pure folds, and its plan mode is soft prompt guidance with no permission gate.
Claude Code's column stores both in live session state and gates edits through the permission mode.

### Named mechanisms

- `tool-todo` package: the model-facing `todo_write` tool. Each call appends a `todo/write` event
  (the full list snapshot) to the owning agent's session log; the current list is last-write-wins on replay.
- `allowParallelInProgress`: required deployment config with no default. It switches the tool description
  and the accepted input between one active task and many.
- `todos` session projection unit: folds `todo/write`, clears on `turn/start`, so UIs render the standing
  plan from the event stream, not from tool results.
- `plan-mode` package: `ctx.planMode` (`PlanModeController`). `plan/mode { active }` is a log-only event;
  `foldPlanMode(events)` recovers the state on resume, fork, and compaction with no live mirror.
- `plan:policy` prompt section: while plan mode is active, deployment-owned guidance text renders into the
  system prompt at order 50. Plan mode is soft guidance; sandbox mode and approval policy enforce
  restrictions independently and never read plan state.
- `exit_plan_mode` tool and `/plan` command: the exit tool stays registered even while plan mode is off, so
  toggling plan mode never changes the request tool catalog. It requires a markdown plan and routes review
  through the user-questions seam; keep-planning returns as a failed call carrying the user's feedback.
- Pending selections: a user's plan-mode flip stays pending until the next accepted in-turn `agent/pre-step`
  appends it, and a `user/message` notice tells the model its context changed.

### Source anchors

- `packages/todo/tool-todo/src/index.ts`: `todo_write`, the `todo/write` append, validation.
- `packages/todo/tool-todo/README.md`: `allowParallelInProgress`, single-owner scope, the `todos` projection unit.
- `packages/plan/plan-mode/src/index.ts`: `ctx.planMode`, `exit_plan_mode`, `/plan`, the pre-step append.
- `docs/subsystems/plan.md`: soft guidance, `plan/mode` fold, `plan:policy` at order 50, pending selections.
- `docs/tool-catalog.md`: `todo_write` and `exit_plan_mode` schemas and catalog notes.

### Draft column gist

- Pros: plan and todo state survive restart, fork, and compaction because both are log events under a fold. UIs replay the same events.
- Cons: plan mode enforces nothing by itself. A model can edit files in plan mode unless sandbox or approval policy blocks it separately.
- Why: one append-only session log is the source of truth, so plan state must be an event, and enforcement belongs to the layers that own it.
- How: plan artifact: `todo_write` appends a `todo/write` snapshot event; a projection folds it and clears it when the next turn starts.
- How: plan mode: a log-only `plan/mode` event plus a prompt guidance section. Soft guidance only; no permission flip.
- How: execution gate: none in plan mode itself. `exit_plan_mode` gates the plan review through a human answer, and rejection returns as tool feedback.

### src/ update candidate

No. The section's src already has both tools. dsh's distinct piece is the event-log fold, and the src has no session log to fold over.

---

## Section 6 · Subagents

**Verdict: yes.** The existing column describes one `Agent` tool with built-in personas. dsh makes the
subagent a capability seam with six coexisting named providers, capability flags checked before start, and
a continuation manager for durable multi-turn children. Strong contrast on every existing How row.

### Named mechanisms

- `subagent` package: the seam. `ctx.subagents` (`SubagentRuntime`) is a named provider registry plus
  continuable-child orchestration and durable child discovery.
- Provider range, all implementing `SubagentProvider`:
  - `subagent-spawn-in-process`: fresh in-process child agent, empty conversation.
  - `subagent-fork-in-process`: in-process child seeded with the parent's completed-turn log prefix
    (up to the last `turn/end`, so the open tool-calling turn is excluded and the seed replays balanced).
  - `subagent-acp` and `subagent-dsh-sdk`: fresh out-of-process runtimes (any ACP agent; a full peer
    harness over stdio JSON-RPC), spawned through `ctx.subprocess`.
  - `subagent-claude-code` and `subagent-codex`: one delegated turn to an external product CLI. Each run
    submits one self-contained text task and returns only the final answer.
- `SubagentCapabilities`: static per-provider flags (`outputSchema`, `depthLimit`, `toolFilter`, `persona`).
  The service rejects a request needing a flag the provider lacks with `UNSUPPORTED_CAPABILITY`, never
  accepted-then-ignored. In-process providers advertise all four; out-of-process providers advertise none.
- `inheritsParentContext`: descriptive flag (fork true, all others false) the tool layer uses for truthful
  model-facing wording. It claims nothing about tools or authority.
- Continuable children: one durable child session with at most one process-local Activation.
  `startContinuable()`, `followup()` (enqueue, wake, or cold-resume by Activation state), `interrupt()`,
  and `reportFrom()`. The child's agent inbox is the only turn queue.
- `subagent/descriptor`: a log-only durable identity event folded last-wins for `listChildren()` and
  `listDescendants()` enumeration without loading any agent.
- Model-facing consumers: `tool-subagent` registers one delegation tool per composed backend (the shipped
  compositions expose `subagent` as continuable and `subagent_fork` as one-shot); `tool-subagent-control`
  adds `send_message`, `interrupt_agent`, `list_agents`; `tool-subagent-report` adds the child-scoped `report`.
- Result contract: `SubagentRun.result` resolves a `SubagentResult` with `stopReason`
  (`completed`, `aborted`, `error`, `max-tokens`, `refusal`); non-completed maps to an `isError` tool result.

### Source anchors

- `packages/subagent/subagent/src/index.ts` and `src/types.ts`: `ctx.subagents`, provider contract, capabilities, result.
- `packages/subagent/subagent/src/continuation.ts`: Activations, followup routing, ownership graph.
- `packages/subagent/subagent/src/descriptor.ts`: `SubagentDescriptorData`, the durable descriptor.
- `packages/subagent/subagent-spawn-in-process/README.md`: fresh child, all four capability flags true.
- `packages/subagent/subagent-fork-in-process/README.md`: completed-turn seed boundary.
- `packages/subagent/subagent-acp/README.md` and `packages/subagent/subagent-dsh-sdk/README.md`: out-of-process runtimes.
- `packages/subagent/subagent-claude-code/README.md` and `packages/subagent/subagent-codex/README.md`: one-task product-CLI delegation.
- `docs/subsystems/subagent.md`: seam overview, continuable children, enumeration, stop reasons.
- `docs/tool-catalog.md`: `subagent`, `subagent_fork`, `send_message`, `interrupt_agent`, `list_agents`, `report`.

### Draft column gist

- Pros: one seam covers in-process children, external runtimes, and product CLIs. Capability checks fail loud. Durable children resume cold.
- Cons: six providers and a continuation manager cost far more machinery than one tool. Out-of-process children enforce no depth, filter, or persona.
- Why: delegation is a transport choice, so providers register by name and the tool layer only picks one. Long tasks need children that outlive a tool call.
- How: spawn primitive: a per-provider delegation tool over a named registry; the range runs fresh child, parent-seeded fork, external runtime, product CLI.
- How: context isolation: spawn starts empty; fork seeds the parent's completed turns only; every out-of-process child gets just the workspace cwd.
- How: result return: the last non-empty assistant message, plus optional schema-validated structured output; non-completed stop reasons return as tool errors.
- How: resume: continuable children accept `send_message` follow-ups through their inbox and cold-resume from the persisted session log.

### src/ update candidate

Yes. Add a fork variant of the `Agent` tool that seeds the child with the parent's completed messages, next to the existing fresh-context spawn.

---

## Section 7 · Skills

**Verdict: yes.** Claude Code's column loads skills through a `Skill` tool from fixed sources; Hermes adds
store evolution. dsh is distinct on where the catalog lives (durable session history kept fresh by digest
replacement, not the system prompt), on discovery (a provider seam with layered scopes and watchers), and
on invocation policy (model and user invocability as separate flags).

### Named mechanisms

- `skill` package: `ctx.skills` (`SkillRegistry`), a provider registry merging skill catalogs. Layered
  host plus per-scope: a preset-mounted plugin's skills exist only for that agent scope; the nearest layer
  wins duplicate names. Emits `skills/change` as an unfiltered invalidation event.
- `skill-filesystem` provider: scans ranked roots (`.dsh/skills` rank 100, `.agents/skills` 200, custom 300,
  user roots 400 and 500, bundled 600); accepts `<name>/SKILL.md` bundles and flat `<name>.md` files;
  chokidar watches roots and model `write`/`edit` observations invalidate the catalog synchronously.
- `skill-badge` provider: registers one immutable packaged (`bundled`) skill and exposes its asset
  directory through `resourceBase`; shipped disabled, enabling it is an explicit composition opt-in.
- `tool-skill` consumer: injects the initial catalog as a durable user-role `<system-reminder>` at the first
  `agent/pre-step` with a complete snapshot. Before each later step it digests the rendered
  `<available_skills>` entries; a changed digest appends a full replacement catalog via `agent.inject()`.
  Incomplete snapshots preserve the last-good model view.
- Model-facing `skill({ name })` tool: validates the kebab-case name, rejects unless `modelInvocable`,
  rereads the body, and returns `<skill_content>`, `<skill_resources>`, `<skill_instructions>`.
- `SkillInvocationPolicy`: frontmatter keys `disable-model-invocation` and `user-invocable` normalize into
  independent model and user flags, so a skill can be model-only, user-only, both, or trusted-caller-only.
- `SkillCatalogSnapshot.complete`: discovery distinguishes authoritative absence from provider failure;
  incomplete observations are never cached.

### Source anchors

- `packages/skill/skill/src/index.ts`: `SkillRegistry`, layering, `skills/change`, snapshot semantics.
- `packages/skill/skill-filesystem/src/index.ts`: ranked roots, watchers, git-root project detection.
- `packages/skill/skill-badge/src/index.ts`: the packaged badge provider.
- `packages/skill/tool-skill/src/index.ts`: catalog injection, digest replacement, the `skill` tool.
- `docs/subsystems/skills.md`: provider contract, rank table, invocation policy, session catalog contract.
- `docs/tool-catalog.md`: the `skill` tool schema and its catalog-injection note.

### Draft column gist

- Pros: the catalog is durable history, so a resumed session still knows its skills, and a digest keeps it fresh without rewriting the prefix each turn.
- Cons: catalog replacements add messages to history. Provider layering, watchers, and completeness states are heavy next to a startup scan.
- Why: skills come from many sources that change while a session runs, so discovery is a live seam and the model view must track it explicitly.
- How: skill format: `SKILL.md` bundles or flat `.md` files, kebab-case names, invocation flags in frontmatter.
- How: load trigger: the `skill({ name })` tool rereads the body on demand; the catalog itself is injected user-role history, replaced when its digest changes.
- How: discovery: registered providers merge over scope layers; the filesystem provider scans six ranked roots and watchers invalidate on change.

### src/ update candidate

No. The section's src teaches progressive disclosure and store evolution. dsh's distinct pieces
(scoped provider seam, digest-replaced catalog) need registry and session machinery the src does not carry.

---

## Section 8 · Context management

**Verdict: yes.** The strongest of the four. Claude Code's column layers in-place reducers over `messages[]`;
mini-swe-agent truncates at render time. dsh never edits history: the log is append-only, the model view is
a projection, and compaction appends replacement events under a durable lock. Spill, pruning, and metering
are separate owned services.

### Named mechanisms

- `deriveMessages()` over the session log: every message-producing event declares a `surfaceOp`, and
  `Session.deriveMessages()` folds the ordered surface into the `Message[]` the model sees. Cached per node,
  deep-frozen, so mutating logged history through a projection is unrepresentable.
- `compaction` package: the compaction seam. `ctx.compaction` (`CompactionEngine`) exposes
  `compactIfNeeded(agent, trigger, signal)` for `pressure` and `context-overflow`, `compactNow()` for idle
  manual runs, and `compactRegion()` for an explicit span. There is no model-facing compact tool.
- Durable lock bracket: `compaction/start`, `compaction/summary`, `compaction/end` are log-only events.
  The summary itself rides on a `user/message` with `surfaceOp: { op: 'replace', start, end }`, the only
  surface mutation. A crash leaves a detectable orphaned start instead of a false end.
- `compaction-basic` backend: compacts at `floor(routedContextWindow x thresholdRatio)` (default 0.8),
  keeps a recent tail (`retainRatio` default 0.16), preserves tool-call/result pairing, retries under
  `compactionRetries`, and rejects a summary that does not shrink its source. The summarize call replays
  the conversation's own prefix verbatim to reuse the provider's warm cache. Provider-confirmed overflow
  enters through `agent/request-error` and attempts one maximal balanced head reduction.
- `ctx.toolResultPruner` (`compaction-tool-result-pruner`): deterministic head/middle/tail pruning of
  oversized tool results before summary compaction; each replacement cites the shadowed node and lands a
  `compaction/prune` shadow-price event, and a remeasure can skip summarization entirely.
- `ctx.tokenMeter` (`token-meter`): replay-based pressure measurement at one consumed log revision.
  Reuses the latest provider usage as a baseline anchor when the request envelope matches, else reprices
  with a fixed heuristic; returns per-node surface prices in positional order.
- `ctx.spillStore` spill seam: `saveText()` persists a tool's oversized text and returns an opaque locator,
  byte count, and retrieval hint. `spill-local` writes private (0700 root, 0600 exclusive-create) files
  under a per-session hash directory. `spill-policy` is a `tools/post-execute` transformer: a plain-text
  result over `maxInlineBytes` is saved in full and replaced with a head/tail preview plus the locator and
  a read-or-grep hint, best effort (a save failure keeps the inline result).

### Source anchors

- `docs/subsystems/session.md`: `deriveMessages()`, `surfaceOp`, projection rules.
- `packages/compaction/compaction/src/index.ts` and `src/types.ts`: `CompactionEngine`, triggers, result, events.
- `docs/subsystems/compaction.md`: the event bracket, lock semantics, pressure and overflow paths.
- `packages/compaction/compaction-basic/README.md`: thresholds, retention, prune-first order, cache-reusing summarize, overflow recovery.
- `packages/compaction/compaction-tool-result-pruner/src/index.ts`: `pruneSession()`, shadow-price events.
- `packages/llm/token-meter/src/index.ts` and `docs/subsystems/token-meter.md`: `measure()`, usage baselines, surface nodes.
- `packages/spill/spill/src/index.ts`: `SpillStore.saveText`, locator and retrieval-hint contract.
- `packages/spill/spill-local/src/store.ts`: private session-scoped file layout.
- `packages/spill/spill-policy/README.md`: `maxInlineBytes`, the post-execute replacement, best-effort rule.

### Draft column gist

- Pros: history is never destroyed; every reduction is an appended, replayable event, and a crash mid-compaction is detectable. Spilled output is re-readable in full.
- Cons: the log only grows on disk, and the seam needs locks, folds, and pairing checks that in-place trimming never pays for.
- Why: the append-only log is the source of truth, so the model view must shrink by projection, not by editing what happened.
- How: trigger: token-meter pressure at every pre-step against a routed threshold, plus provider-confirmed overflow through request-error recovery.
- How: strategy: spill oversized results at tool time, prune old tool results deterministically, then one summary event that replaces the span in the projection.
- How: budget: capacity-scaled ratios per routed model (compact at 0.8, retain 0.16 verbatim), with per-model overrides.

### src/ update candidate

Yes. Adopt spill: the current `_budget` pass only truncates with a `<persisted-output>` marker
(`sections/08-context-management/src/context.py`) and never writes the text anywhere. A small spill store
can save the full result to a session-scoped file at tool-result time and leave a head/tail preview plus
the path and a retrieval hint, so the agent can read the full output back.
