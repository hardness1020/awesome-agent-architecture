# deepseek-harness (dsh) · research notes for sections 0, 19-23

Pinned tag: `dsh-v0.1.0-rc.7`. Resolves ticket #69 of wayfinder map #63.

Criterion: a dsh column earns its place only on a real, source-verifiable mechanism that contrasts with the
existing Claude Code, Hermes Agent, and mini-swe-agent columns of each section. All paths below are dsh repo
paths at the pinned tag.

## Shared background

- dsh runs on Cordis, a vendored plugin framework. A plugin contributes services, typed events, and
  reversible effects to a shared context; registrations unwind on unload (`docs/cordis-primer.md`).
- Every product part is a plugin: the model adapter, the tool registry, the session log, and the agent loop
  itself. There is no privileged core to patch (`docs/architecture.md`).
- A capability seam has three roles: Service Definition, Service Provider, Consumer. One provider swap moves
  the whole product, e.g. fs plus subprocess to a remote sandbox (`docs/capability-seams.md`).
- Boot composes ordered layers: each bundle in the profile's order, the profile's `cordis.patch.yml`, the
  home-level one, then `--patch` overlays. A patch targets a row by id and replaces its whole config
  (`docs/architecture.md`, `packages/boot/app-boot/README.md`).
- Events declare a dispatch mode (`emit`, `waterfall`, `parallel`, `serial`). A waterfall listener returns
  without `next()` to own the decision (`docs/cordis-primer.md`).

---

## Section 0 · Harness thesis

**Verdict: yes, a thesis-level mention is earned. Borderline for a full column.**

"Everything is a plugin" is the repo's own headline (`README.md`), and `docs/architecture.md` makes it a
mechanism claim: every part is a plugin, so every part is replaceable from configuration. That is a third
position on section 0's harness-size axis. Claude Code: the harness is the main code surface. mini-swe-agent:
almost no harness. dsh: a large harness with no fixed core, where each layer swaps or deletes from config.
It operationalizes section 0's rule to re-evaluate each layer on model change: deleting a layer is unloading
a plugin, and `dsh --profile web --dump-config` prints every replaceable row (`docs/architecture.md`).

- Named mechanisms: Cordis services on `ctx.<key>`, `inject` dependency declarations, reversible effects via
  `ctx.effect()` (`docs/cordis-primer.md`); the seam triple (`docs/capability-seams.md`); the loop as one
  plugin, `ctx.agentLoop` (`docs/subsystems/core.md`).
- Draft column gist. Pros: any layer swaps or deletes from config; `examples/agent-spine-demo` proves even
  the loop is one plugin. Cons: a framework to learn before any feature; behavior scatters across dozens of
  packages and their events (`packages/`, `docs/module-graph.md`). Why: assumes the harness keeps changing,
  so replaceability is the design center (`docs/architecture.md`). How rows: model owns judgment and stop
  decisions; harness owns everything else, each part a plugin; size signal: the loop driver is one package
  among dozens, and extension packages never import it (`docs/subsystems/core.md`).
- src/ update candidate: no. Section 0 has no `src/`.

---

## Section 19 · MCP / plugins / channels

**Verdict: yes.**

Contrast: Claude Code merges server config by scope precedence over six transports; Hermes gates inbound
chat channels. In dsh an MCP server is one plugin instance in the composition, hot-swapped by HMR, with
generation-swap re-sync and a budgeted reconnect supervisor. The plugin format is patchable config rows, not
a manifest bundle.

Named mechanisms and anchors:

- `@deepseek-ai/dsh-mcp-client`: one plugin instance per server in `cordis.yml`; transports `stdio` and
  `streamable-http` (`packages/mcp/mcp-client/README.md`).
- Naming: public name `mcp__<serverName>__<rawName>`, normalized to 64 chars of `[A-Za-z0-9_-]`; when
  replacement or truncation changes the name, a deterministic 12-hex hash of `(serverName, rawName)` is
  appended (`packages/mcp/mcp-client/src/tools.ts`).
- Generations: `notifications/tools/list_changed` re-syncs; a fetch failure keeps the previous generation
  registered; a registration conflict rolls the whole attempted generation back, never a partial set
  (`packages/mcp/mcp-client/README.md`, Behavior).
- Reconnect supervisor: exponential backoff with a per-outage `maxAttempts` budget; a connection that
  survives past `maxDelayMs` resets the budget, so a crash-looping server exhausts the cap while an
  occasional crasher recovers indefinitely (`packages/mcp/mcp-client/README.md`).
- HMR hot-swap: editing the entry disconnects and reconnects without process restart; an unchanged
  `serverName` reproduces identical tool names (`packages/mcp/mcp-client/README.md`, Usage).
- Scope: tools are the only bridged MCP capability; Resources and Prompts are deferred
  (`packages/mcp/mcp-client/README.md`, Known Limitations).
- Plugin format: bundles and profiles declare themselves under a `dsh` field in `package.json`; layers apply
  in order and a user patch replaces the matched row's whole config (`docs/architecture.md`,
  `packages/boot/app-boot/README.md`).
- Per-session composition: agent presets mount one preset `cordis.yml` under an agent scope; a service row
  there needs an `isolate` realm (`docs/architecture.md`, `packages/preset/agent-presets/src/index.ts`).
- Channels: no chat channels. An ACP stdio server lets programmatic clients create and drive fresh agents
  (`packages/acp/acp/README.md`). `ctx.commands` dispatches human commands without a model turn
  (`docs/architecture.md`). The model can define, run, and stop in-process Cordis plugins through
  `cordis_define` and `cordis_run`, session-scoped and memory-only (`packages/extensions/tool-cordis/README.md`).

Draft column gist:

- Pros: a server is config: hot-swap without restart, and a bad re-sync rolls back whole.
- Cons: tools only, no Resources or Prompts; no chat channels, so nothing pushes messages in.
- Why: everything is a plugin, so MCP joins as one plugin instance per server, not a separate subsystem.
- How: transports: stdio and streamable-http, one plugin instance per server, with a budgeted reconnect
  supervisor. How: plugin format: Cordis config rows; profiles stack bundles, two patch files, then
  overlays, and a patch replaces a row's whole config by id. How: tool pool assembly: each discovered tool
  registers on the scoped registry under `mcp__server__tool`; a re-sync swaps the server's whole generation
  or rolls back.

src/ update candidate: **yes.** `mcp.py` could adopt generation swap: re-discovery replaces a server's
wrapped tools as one unit and keeps the old set when discovery fails.

---

## Section 20 · Observability & evaluation

**Verdict: yes.**

Contrast: Claude Code queues, samples, and scrubs ad-hoc events; mini-swe-agent saves trajectory files. dsh
exports the durable session log itself: ledger records mirror session events one-to-one through a redaction
waterfall into an OpenTelemetry backend, and the eval feed is feedback-gated.

Named mechanisms and anchors:

- `ctx.sessionTelemetry` seam (`packages/session/session-telemetry`) with the OTel provider
  (`packages/session/session-telemetry-otel`). Two channels: `ledger` mirrors session-log events one-to-one;
  `ops` carries `agent-error` and `shutdown` (`docs/subsystems/session-telemetry.md`).
- Capture trims streams: only the first `assistant/chunk` per `(turn, step)` ships
  (`docs/subsystems/session-telemetry.md`).
- `session-telemetry/record` waterfall: the seam ships no redaction rules of its own; a throwing listener
  withholds that one record, fail-closed; the canonical log is never rewritten
  (`packages/session/session-telemetry/src/index.ts`, `docs/subsystems/session-telemetry.md`).
- Backend contract: `emit()` must be a non-blocking enqueue; batching, retry, and loss policy belong to the
  reporting SDK; delivery is best-effort and receivers dedupe on `(session.id, event.seq)`
  (`docs/subsystems/session-telemetry.md`).
- Sharing disclosure: `full`, `feedback-only`, `disabled`; under `feedback-only`, recording feedback releases
  the session prefix for sharing (`packages/feedback/command-feedback/README.md`).
- `/feedback` appends one log-only `feedback/record` event; it never enters model requests and starts no
  model turn (`packages/feedback/command-feedback/README.md`).
- `ctx.messageFeedback`: per-assistant-message ratings in a compare-and-set storage sidecar, outside the
  session log and outside telemetry (`docs/subsystems/feedback.md`,
  `packages/feedback/message-feedback/src/index.ts`).
- `ctx.tokenMeter` (`packages/llm/token-meter/README.md`): one fixed heuristic, four characters per token,
  anchored to provider-reported usage; `projectedTokens` prices the next request after compaction shadows a
  span; occupancy is a reference figure and nothing gates on it; compaction reads `measure()`.
- `ctx.invariants` (`packages/runtime-diagnostics/invariants/src/index.ts`): every workspace package
  publishes a `./invariant` companion; a violation throws a package-attributed `InvariantError`; a repo gate
  rejects unexplained empty installers (`docs/subsystems/invariants.md`).
- `BENCHMARK.md` is three lines: run external benchmarks through the Python SDK `jsonrpc-agent` minimal
  variant with separate workspaces and session ids per task (`BENCHMARK.md`, `docs/user/guide/python-sdk.md`).

Draft column gist:

- Pros: nothing extra to instrument: model-visible means logged, so the export mirrors the one source of
  truth, and redaction fails closed.
- Cons: ships no redaction rules; delivery is best-effort with loss and duplicates; prices tokens, never
  dollars.
- Why: the append-only session log is already the record, so observability exports it instead of keeping a
  second event stream.
- How: telemetry: a seam mirrors each session event as a ledger record through a redaction waterfall into an
  OTel log pipeline, with ops signals on a second channel. How: cost tracking: a replay fold prices the log
  with one fixed heuristic anchored to provider-reported usage and projects the next request's prompt cost.
  How: eval feed: feedback-gated: `/feedback` writes a log-only event, and feedback-only mode releases the
  session prefix for sharing; recorded logs replay keyless as fixtures.

src/ update candidate: **yes.** `telemetry.py` could derive events from the session record instead of ad-hoc
emits, or make `scrub` a fail-closed chain that withholds a record when a rule throws.

---

## Section 21 · Loop engineering

**Verdict: yes.**

Contrast: the existing columns compose outer loops around the process (verify scripts, cron, curators). dsh
publishes the loop's own seams as events, so outer loops attach inside it as plugins: inbox admission,
pre-step rewrites, request-error retries, turn-stopping steering. The loop itself is one replaceable plugin.

Named mechanisms and anchors:

- `ctx.agentLoop` is the one concrete driver; extension packages depend on `dsh-agent` events and services,
  never on the loop package, so the loop stays swappable; `examples/agent-spine-demo` wires the spine
  (`docs/subsystems/core.md`, `docs/capability-seams.md`).
- Inbox admission: two ordered pending lists, `next-turn` and `next-step`; `followup` wakes the driver,
  `steer` targets the nearest step, `inject` parks until another message wakes it; `claim` removes the
  proposed step batch (`packages/core/agent/src/types.ts`, `docs/subsystems/core.md`).
- `agent/pre-step` waterfall: reject a proposed step or replace its messages; a rejected or empty first
  claim still closes a durable turn that spent no step, so the log records the attempt
  (`packages/core/agent/src/runtime-types.ts`, `docs/architecture.md` Turn flow).
- `agent/request-error` waterfall: a listener returns `{ kind: 'retry' }` to own recovery; compaction-basic
  uses it for canonical context overflow (`docs/subsystems/core.md`, `docs/agent-lifecycle.md`).
- `agent/turn-stopping` serial checkpoint: a listener objects by steering and the machine re-reads its
  inbox; data decides, so listener order cannot change the outcome (`docs/subsystems/core.md`).
- Goal loop: `ctx.goals` folds one objective from the log with a round cap and a blocked phase;
  `goal-round-driver` reserves round n+1 at idle, queues one `<goal_round>` prompt, verifies it in
  `agent/pre-step`, and only an entered message increments `roundsStarted`; cancellation pauses the goal so
  it cannot auto-restart (`packages/goal/goal/README.md`, `packages/goal/goal-round-driver/README.md`).
- Ralph loop: `tool-ralph` runs a fixed fresh-agent iteration over `ctx.workflowEngine`; completion is a
  worker report, an independent evaluator is named deferred work; only round count bounds effort
  (`packages/workflow/tool-ralph/README.md`).
- Event loop: `dsh-schedule` stores reminders as session events; timers are disposable projections of the
  log; a due reminder claims the idle phase through `runMaintenance()` and enters as an ordinary
  `followup()` turn (`packages/schedule/schedule/README.md`).

Draft column gist:

- Pros: outer loops attach as plugins on the loop's published admission events; every attempt leaves a
  durable record, even a rejected zero-step turn.
- Cons: no checker anywhere: goal and Ralph completion are self-declared; round counts are the only budget,
  token and time budgets are deferred.
- Why: the loop is one replaceable plugin, so control is designed as events on it rather than wrappers
  around it.
- How: verification: none built in; the goal prompt demands evidence, and Ralph names its missing evaluator
  as deferred. How: event loop: reminders fold from the session log; a due one claims the idle phase and
  enters as an ordinary follow-up turn. How: improvement loop: none shipped; the seams one would need
  (pre-step rewrite, request-error retry, turn-stopping steer) exist as plugin-attachable events.

src/ update candidate: **yes.** The loop could add a pre-step admission gate: queued messages pass a
reject-or-rewrite hook before a step opens, and a rejected claim is still recorded.

---

## Section 22 · Graph engineering

**Verdict: borderline, lean no.**

Reasoning: the section's core question is who decides the next node. dsh answers exactly as the existing
Claude Code column: the model writes a per-run imperative script, code runs it, and nothing is a declared
graph. dsh's own doc says its `meta` field vocabulary matches the Claude Code dynamic-workflows meta block
(`docs/subsystems/workflow.md`). What dsh adds is execution substrate, not routing design: one worker thread
per run with a vm inside, an engine behind a swappable seam, a JSON materialization boundary, and no journal
or resume. That grounds the existing per-run-script cells with source-verified evidence, but a fourth column
would repeat the Claude Code answers on nodes and routing. Recommendation: cite dsh in section 22's Sources
as the source-verifiable sibling of the Claude Code `Workflow` contract, without a column.

Named mechanisms and anchors:

- `ctx.workflowEngine` seam; one engine per context, no named-provider registry
  (`docs/subsystems/workflow.md`).
- `dsh-workflow-worker-thread`: one `node:worker_threads` worker per run, the script's `node:vm` context
  inside it; the split keeps a synchronous script off the harness event loop and gives disposal a real stop
  via `worker.terminate()`; explicitly not a security boundary
  (`packages/workflow/workflow-worker-thread/README.md`, `packages/workflow/workflow-worker-thread/src/runtime.ts`).
- Script hooks: `agent()`, `parallel()`, `pipeline()`, `phase()`, `log()`; children start host-side through
  `ctx.subagents`; phases are narration with no execution semantics
  (`packages/workflow/workflow-worker-thread/README.md`).
- `meta` is data validated before the body runs; return values pass `materializeFromRealm`, which rejects
  non-JSON and defines keys as data properties so `__proto__` cannot mutate a prototype
  (`packages/workflow/workflow-worker-thread/README.md`, Value boundary).
- Caps are engine config the script cannot observe: `maxConcurrentAgents`, `maxTotalAgents` (default 1000),
  `maxItemsPerCall`, `syncTimeoutMs`, `disposeGraceMs` (`packages/workflow/workflow-worker-thread/README.md`).
- `run.result` never rejects; cancellation force-settles within a bounded grace; `dispose()` awaits child
  quiescence (`docs/subsystems/workflow.md`).
- Foreground only: the parent turn blocks until the run settles; no background start and no resume
  (`packages/workflow/tool-workflow/README.md`, Known Limitations).
- Durable records are observational: `tool-workflow/run-start` and `run-end`; a failed append degrades to a
  legal prefix without changing execution (`docs/subsystems/workflow.md`).

Draft column gist (recorded in case the column is promoted anyway):

- Pros: the script runs off the host event loop and termination is real; caps and provider choice are
  policy the script cannot see.
- Cons: the parent turn blocks until the run settles; no journal, so a dead run restarts from nothing; the
  vm is not a security boundary.
- Why: known structure is disposable, so the model writes a fresh imperative program per run and the
  harness only bounds and observes it.
- How: nodes: each `agent()` call is one fresh child through the subagent seam. How: routing: plain JS
  control flow the model wrote; phases are narration, not edges. How: state: worker-realm variables; only
  the materialized final JSON value crosses to the parent.

src/ update candidate: **no.** `graph.py` teaches coded edges; a model-written script engine would replace
the section's mechanism, not extend it.

---

## Section 23 · Evaluation

**Verdict: no, borderline.**

Reasoning: the section grades agent quality with environments that reset, simulated users, rubrics, and
repeats. dsh at this tag ships none of that. `BENCHMARK.md` is three lines: install the Python SDK, run the
`jsonrpc-agent` minimal variant, use separate workspaces and session ids per task; grading happens in
whatever external harness calls it (`BENCHMARK.md`, `docs/user/guide/python-sdk.md`). What dsh does ship is
harness regression testing: record one real run, then replay it keyless, with snapshot suites diffing
normalized transcripts and re-persisted logs (`docs/testing.md`). The policy doc itself separates the two:
a no-key test proves plumbing, only a with-key run proves the agent works, and assertions must verify the
world, not the self-report (`docs/testing.md`). Replay pins behavior; it cannot say a change made the agent
better. Best use: cite the record-replay corpus in section 20's eval-feed row and keep 23 without a dsh
column.

Named mechanisms and anchors:

- `llm-replay`: a replay LLM adapter behind the same `ctx.llm` seam; the fixture IS the persisted session
  JSONL, so recording is "run the real agent once and harvest the log"
  (`packages/test-support/llm-replay/README.md`).
- Sidecar overrides inject the two unrecordable failures, a pre-chunk throw and a hang; live sessions bind
  to recorded scripts by first-call order; `{{fromRequest:<regex>}}` fills values only the live request
  knows (`packages/test-support/llm-replay/README.md`).
- Snapshot tiers: `test:snapshot` and `test:web` replay recorded sessions and diff normalized JSON-RPC,
  browser output, and re-persisted logs; record and refresh stay local and every diff is reviewed
  (`docs/testing.md`).
- With-key policy: real-API e2e smokes boot the real example, send one prompt, and check the world; suites
  self-skip without a key (`docs/testing.md`).
- Coverage gate: per-file 100 percent on `packages/*/*/src`, stated as necessary but never sufficient
  (`docs/testing.md`).

Draft column gist (recorded for completeness):

- Pros: fixtures are harvested real runs; replay is keyless and deterministic through the same model seam.
- Cons: nothing is graded: no task set, no rubric, no environment reset; quality claims defer to external
  benchmarks.
- Why: assumes external harnesses grade quality; the repo's own suites guard the harness, not the model.
- How: environment: the recorded session log replayed through the model seam. How: task set: snapshot
  scenarios per runnable example. How: scoring: byte diff of normalized transcripts and re-persisted logs.
  How: repeats: none; replay is deterministic.

src/ update candidate: **yes.** `evaluation.py` could record one live episode's model stream and replay it
as the offline test's scripted model, keeping demo and test on one corpus.
