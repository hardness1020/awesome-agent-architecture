# deepseek-harness research notes · sections 1 to 4

Pinned tag: `dsh-v0.1.0-rc.7`. All paths below are relative to the deepseek-harness repo root.
Scope: distinctive-only verdicts for a possible dsh column in sections 1 (agent loop), 2 (tool runtime),
3 (permission and sandbox), 4 (hooks), judged against the existing Claude Code and mini-swe-agent columns.

Background every section leans on: dsh is built on Cordis. Every part is a plugin, including the loop,
the tool registry, and the model adapter, and plugins communicate through typed events dispatched as
`emit`, `waterfall`, `parallel`, or `serial` (`docs/architecture.md`, `docs/cordis-primer.md`).
A waterfall listener receives `(...args, next)`. It calls `next()` to delegate or returns without
`next()` to short-circuit and own the decision (`docs/cordis-primer.md`).

---

## Section 1 · Agent loop

**Verdict: yes.** The loop is a replaceable plugin driving a durable event log, with typed interception
waterfalls at each phase. That contrasts with Claude Code's in-runtime async generator and
mini-swe-agent's while loop, on every existing How row.

### Named mechanisms

- `dsh-agent-loop` (`ctx.agentLoop`): the one concrete driver implementing the public `Agent`
  contract declared by `dsh-agent` (`ctx.agents`). Extensions depend on `agent`, never on
  `agent-loop`, so the loop stays swappable (`docs/subsystems/core.md`).
- Turn and step vocabulary: a step is one model request plus the tools it calls; a turn is zero or
  more steps, open from first claim until nothing is owed (`docs/architecture.md`, Turn flow).
- The inbox: two ordered pending lists, `next-turn` and `next-step`. `followup`, `steer`, and
  `inject` are fixed presets of one `send(message, target, wakeup)` method
  (`packages/core/agent/src/types.ts`, `docs/subsystems/core.md`).
- Loop waterfalls: `agent/pre-step` rejects a proposed step or replaces its claimed messages;
  `agent/request` replaces the frozen call config; `agent/request-error` returns `{ kind: 'retry' }`
  to own recovery (`packages/core/agent/src/runtime-types.ts`, `docs/subsystems/core.md`).
- Stop conditions: the turn closes when the model owes nothing (no live tool calls, no fresh
  steering) and the `agent/turn-stopping` serial checkpoint objects with data, not order. A listener
  that objects calls `agent.steer()` and the machine re-reads its inbox. A tool result carrying
  `concludesTurn` ends the turn at its step (`docs/subsystems/core.md`,
  `packages/core/agent-loop/src/agent.ts`, `packages/core/agent-loop/src/tool-calls.ts`).
- No max-step budget in the driver. `turn/end` records a typed reason: `completed`, `blocked`,
  `max-tokens` (sticky), `aborted` with a typed `AgentCancelCause`, or `error`
  (`packages/core/agent-loop/src/agent.ts`).
- Durable log as loop state: `messages` is not a buffer the loop owns. Model history is derived
  from the append-only `SessionEvent` log by `deriveMessages()`, and a runtime invariant asserts
  model-visible means logged (`docs/architecture.md`, Session log).

### Source anchors

- `docs/architecture.md` (Turn flow, Events, Session log)
- `docs/agent-lifecycle.md` (full turn and step sequence diagram)
- `docs/subsystems/core.md` (Agent handle, inbox, interception decisions, `agent/*` catalog)
- `packages/core/agent-loop/src/agent.ts` (turn close, `agent/turn-stopping`, `TurnEndReason`)
- `packages/core/agent/src/types.ts` (`Agent`, `InboxTarget`, `AgentCancelCause`)

### Draft column gist

- Pros: the loop is swappable from config; every phase is interceptable; the log replays exactly.
- Cons: the most moving parts of the three; a reader needs turn, step, inbox, and event vocabulary.
- Why: assumes the loop itself is product surface, so it ships as one plugin among peers.
- How, loop driver: a `dsh-agent-loop` plugin behind the `Agent` interface; state derives from the log.
- How, stop signal: nothing owed plus the `agent/turn-stopping` checkpoint; `concludesTurn` on a result.
- How, parallel tools: yes, exclusive barriers plus a bounded rolling pool by execution mode.
- How, streaming: yes, `llm/stream` chunks land as durable `assistant/chunk` events.

### src/ update candidate

No. The section's `run_turn` teaches the minimal branch; inbox targets and durable turn records
belong to later sections (5 and beyond), not this one.

---

## Section 2 · Tool runtime

**Verdict: yes.** A scoped registry with a guarded execution pipeline contrasts with Claude Code's
flat permission-filtered pool and mini-swe-agent's single bash tool on every existing How row.

### Named mechanisms

- `dsh-tools` (`ctx.tools`): the scoped tool registry and guarded execution pipeline
  (`docs/architecture.md`, Core packages).
- `ToolDefinition`: model-facing `ToolSchema` plus a mandatory `output` contract
  (`schema` + pure `render`), the `execute` body, optional `finalizeContent`, `timeoutMs`,
  `isConcurrencySafe(args)`, and pure `presentCall`/`presentResult` UI presenters. `schemas()`
  projects by explicit allowlist so callbacks never leak into a model request
  (`docs/subsystems/tools.md`).
- `defineTool` DSL: one `ValueSchemaSpec` vocabulary types parameters and output; `validateArgs()`
  rejects with `ToolArgsError`, an invalid body value throws `ToolOutputError`
  (`packages/core/tools/src/schema.ts`, `docs/subsystems/tools.md`).
- Scoped registration and `ToolRestriction`: tools registered through `agent.ctx` shadow globals;
  a per-scope allow/deny mask filters inherited globals, restrictions intersect, and a scope's own
  registrations stay exempt (`docs/subsystems/tools.md`).
- The pipeline: `tools/pre-execute` (allow, deny, ask waterfall), then registered monotonic
  guards, then `tools/execute` (around-dispatch wrappers), then `tools/post-execute` (accept,
  replace, block), then definition-owned `finalizeContent`, then `tools/result`, the frozen
  authoritative outcome (`docs/tool-execution-pipeline.md`, `docs/subsystems/tools.md`).
- Argument fidelity as a rule: pre-policy cannot rewrite arguments, because history, audit, UI,
  and execution must agree (`docs/subsystems/tools.md`).
- Scheduling: `executionMode()` classifies each pending call `parallel` or `exclusive`, fail
  closed; the loop forms barriers and a bounded rolling pool (`docs/subsystems/tools.md`,
  `docs/agent-lifecycle.md`).
- Code Mode: the reserved `run_code` transport dispatches serialized sub-calls through the same
  pipeline, carrying the parent token and logging `tool/code-dispatch`
  (`docs/tool-execution-pipeline.md`).
- Unknown tool: `ToolNotFoundError` maps to `UNKNOWN_TOOL` and the call fails without ending the
  turn (`docs/subsystems/tools.md`).

### Source anchors

- `docs/subsystems/tools.md` (`ToolDefinition`, DSL, restriction, pipeline types, `ctx.tools` API)
- `docs/tool-execution-pipeline.md` (pipeline flow diagram)
- `packages/core/tools/src/index.ts` (registry, pipeline, events)
- `packages/core/tools/src/schema.ts` (`defineTool` schema DSL)

### Draft column gist

- Pros: per-agent tool sets without forking the registry; every call passes one auditable pipeline.
- Cons: a tool must declare an output schema and renderer, so simple tools carry ceremony.
- Why: one visibility resolver should feed presentation, lookup, and dispatch, per scope.
- How, tool definition: schema plus typed output contract, body, and pure UI presenters.
- How, dispatch: scope-aware lookup, then a five-stage guarded pipeline around the body.
- How, parallel calls: per-call classifier, fail closed to exclusive; barriers plus a rolling pool.
- How, discovery: no lazy loading; scoped restriction and presets shape what each agent sees.

### src/ update candidate

Yes. `Registry.get` could take an optional scope with scoped tools shadowing globals, showing
per-agent tool sets in a few lines (mirrors `ctx.tools.register` scoping in
`docs/subsystems/tools.md`).

---

## Section 3 · Permission and sandbox

**Verdict: yes.** Deny-only monotonic guards, a fail-closed approval seam, and argv-wrapping sandbox
providers contrast with Claude Code's mode-plus-rules gate and mini-swe-agent's confirm prompt on
every existing How row.

### Named mechanisms

- `ToolGuard` (registered via `ctx.tools.guard()`): scope-aware final pre-dispatch policy that runs
  after every `tools/pre-execute` listener. Its return type has no allow result. A returned reason
  denies; `undefined` abstains; listener ordering cannot turn a denial back into permission
  (`docs/subsystems/tools.md`).
- `dsh-user-approval` (`ctx.approval`): `request()` requires an open turn, appends the
  `approval/asked` and `approval/decided` audit pair, and dispatches the `approval/request`
  answerer waterfall. `ApprovalOutcome` is closed: `allowed-once` is the only grant; `rejected`,
  `cancelled`, and `unavailable` all deny. A missing or throwing answerer becomes `unavailable`
  (`docs/subsystems/approval.md`).
- Per-session `ApprovalPolicy`: `ask` delegates to answerers; `never` deterministically rejects
  before any answerer, so a later `prepend` cannot bypass it (`docs/subsystems/approval.md`).
- `dsh-sandbox` (`ctx.sandbox`): `confine(argv, policy)` wraps a subprocess argv in a platform
  runner and returns `ConfinedArgv` with an enforcement fact (`full` or `partial`), backend denial
  signatures, and runner-failure rules. Silent unconfined passthrough is forbidden; no backend
  means `SANDBOX_UNAVAILABLE` (`docs/subsystems/sandbox.md`).
- `SandboxMode` governs file effects only: `read-only`, `workspace-write`, `danger-full-access`.
  Network and process visibility are outside the vocabulary (`docs/subsystems/sandbox.md`).
- `dsh-sandbox-policy` (`ctx.sandboxPolicy`): resolves a complete per-call policy. An approved
  explicit mode outranks the session's last `sandbox/mode` event, which outranks the deployment
  default; the session cwd is the workspace-write root (`docs/subsystems/sandbox.md`).
- `dsh-sandbox-local`: probes and caches one platform runner, Linux bwrap then Landlock, macOS
  Seatbelt, Windows ACL restricted token (`packages/sandbox/sandbox-local/README.md`).
- `dsh-bash-sandbox`: spawns the wrapped argv, classifies denials from the backend's own stderr
  dialect as result facts (`sandbox.denied: true`), and separates runner failure from command
  failure (`packages/shell/bash-sandbox/README.md`).
- `dsh-permission-presets` (`ctx.permissionPresets`): named presets bundle the two knobs, sandbox
  mode plus approval policy. Defaults ship `workspace-write` (workspace-write + ask) and
  `danger-full-access` (danger-full-access + never); unmatched knob values derive the read-only
  `custom` state (`docs/subsystems/permission-presets.md`).
- `packages/e2b` (`ctx.e2b`, `ctx.fs`, `ctx.subprocess`): an E2B Linux sandbox as a remote
  execution world behind the filesystem and subprocess seams. It is a sibling of `ctx.sandbox`,
  not a provider of it; bash, terminal, and LSP move with the seams unforked
  (`packages/e2b/README.md`, `docs/subsystems/sandbox.md`).

### Source anchors

- `docs/subsystems/tools.md` (`ToolGuard`, `PreToolDecision`, `ctx.tools.guard`)
- `docs/subsystems/approval.md` (`ctx.approval`, `ApprovalOutcome`, `ApprovalPolicy`, audit pair)
- `docs/subsystems/sandbox.md` (`SandboxMode`, `SandboxPolicy`, `ConfinedArgv`, `ctx.sandboxPolicy`)
- `docs/subsystems/permission-presets.md` (`PresetSpec`, default table, derived `custom`)
- `packages/sandbox/sandbox-local/README.md` (runner selection, fail closed)
- `packages/shell/bash-sandbox/README.md` (denial classification, escalation fields)
- `packages/e2b/README.md` (remote execution world, seam composition)

### Draft column gist

- Pros: denial is monotonic and auditable; sandbox verdicts fail closed and report enforcement gaps.
- Cons: policy spreads across guards, approval, sandbox policy, and presets; more seams to trace.
- Why: assumes no single gate function suffices, so each concern is its own fail-closed service.
- How, gate point: pre-execute waterfall decides allow, deny, ask; deny-only guards run after it.
- How, permission modes: two session knobs, sandbox mode and ask or never, bundled as named presets.
- How, sandbox: providers wrap the argv per call; denials read back as classified result facts.
- How, rule persistence: knob changes are session-log events; replay folds the effective policy.

### src/ update candidate

Yes. Add a deny-only guard list that runs after `decide()`; a guard returns a reason or abstains,
and no guard can re-allow (mirrors `ToolGuard` in `docs/subsystems/tools.md`).

---

## Section 4 · Hooks

**Verdict: yes.** The existing table has only a Claude Code column. dsh's canonical hook surface is
typed in-process waterfall events with `next()` delegation, and external shell hooks arrive through
a compatibility bridge. Both halves are real and source-verifiable.

### Named mechanisms

- Canonical surface: the typed interception points themselves. A native hook is an ordinary Cordis
  plugin listening on `agent/pre-step`, `agent/request`, `agent/request-error`,
  `tools/pre-execute`, `tools/execute`, `tools/post-execute`, and the serial
  `agent/turn-stopping` (`packages/hooks/README.md`, `docs/architecture.md`).
- `next()` semantics: a waterfall listener returns without `next()` to own the decision, or calls
  `next()` to delegate and possibly wrap the downstream result. `agent/turn-stopping` is serial
  and has no `next()`; an objecting listener steers instead, so data decides, not listener order
  (`docs/cordis-primer.md`, `docs/architecture.md`, `docs/subsystems/core.md`).
- Typed decisions instead of exit codes: `PreStepDecision` (reject or enter with messages),
  `PreToolDecision` (allow, deny, ask), `PostToolDecision` (accept, replace, block with feedback),
  `RequestErrorAction` (retry) (`docs/subsystems/core.md`, `docs/subsystems/tools.md`).
- `dsh-hook-protocol`: the shared shell-hook wire library. `parseHookOutput` decodes exit 2 as
  block-with-stderr; `mergeHookOutputs` folds multiple hooks most-restrictively, deny over ask
  over allow; `createDetachedRuns` drains fire-and-forget hooks on dispose
  (`packages/hooks/hook-protocol/README.md`).
- `dsh-hooks-claude-code`: runs a user's existing `hooks.json` command hooks on the harness
  points. `SessionStart` maps to `agent/session-start` plus `agent.inject()`; `UserPromptSubmit`
  to `agent/pre-step`; `PreToolUse` to `tools/pre-execute`; `PostToolUse` to
  `tools/post-execute`; `Stop` to `agent/turn-stopping`, where a blocking hook feeds its reason
  through `steer()` and forces another step. 23 of Claude Code's 30 events are unsupported, and
  `updatedInput` is logged but not honored (`packages/hooks/hooks-claude-code/README.md`).
- `dsh-hooks-codex`: the Codex dialect bridge on the same shared protocol
  (`packages/hooks/README.md`).
- Durable audit: each bridge invocation appends paired `hook/invoked` and `hook/result` session
  events inside an open turn (`packages/hooks/hook-protocol/README.md`).
- Guard family: `dsh-repeat-tool-reminder` and `dsh-timeout-policy` are native plugins on these
  same points, one via `tools/post-execute` contexts, one as a `tools/execute` wrapper
  (`packages/guard/README.md`).

### Source anchors

- `packages/hooks/README.md` (bridges versus the canonical typed surface)
- `packages/hooks/hooks-claude-code/README.md` (event mapping table, limitations)
- `packages/hooks/hook-protocol/README.md` (codec, most-restrictive merge, `hook/*` events)
- `docs/cordis-primer.md` (waterfall dispatch and `next()`)
- `docs/subsystems/core.md` (`agent/*` waterfall and serial catalog)
- `packages/guard/README.md` (native plugins as hooks)

### Draft column gist

- Pros: hooks are typed plugins, not shell subprocesses; existing Claude Code hooks still run.
- Cons: two surfaces to learn; the bridge covers a subset and cannot rewrite tool input.
- Why: assumes the extension surface should be the same event system the harness itself runs on.
- How, hook events: waterfall and serial events per phase; bridges map external dialects onto them.
- How, fire point: `tools/pre-execute` hosts hook policy and approval before deny-only guards.
- How, can block or modify: yes via typed decisions; multiple shell hooks fold deny over ask over allow.

### src/ update candidate

Yes. Let pre-hooks return deny, ask, or allow and fold most-restrictively, deny over ask over
allow, so ordering cannot loosen a decision (mirrors `mergeHookOutputs` in
`packages/hooks/hook-protocol/README.md`).
