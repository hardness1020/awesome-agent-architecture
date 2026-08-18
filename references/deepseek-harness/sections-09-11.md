# deepseek-harness research notes · sections 9 to 11

Research for wayfinder map #63, ticket #66. Source: deepseek-harness at tag `dsh-v0.1.0-rc.7`.
All paths below are paths inside that repo. Doc pages cited are the English files under `docs/`.

---

## Section 9 · Memory

### Verdict

**Cross-run memory: no.** dsh has no distilled memory store, no extraction at run end, and no consolidation.

- The generated persistence catalog enumerates every durable event type. None is a memory record (`docs/persistence-catalog.md`).
- The generated tool catalog enumerates every shipped tool. None writes memory (`docs/tool-catalog.md`).
- The workspace registry is host-side session grouping, "invisible to models (no tools, no prompt text, no session events)" (`docs/subsystems/workspace.md`).
- `ctx.goals` is "event-sourced same-session goal state". It lives in the session's own log as `goal/change` events (`packages/goal/goal/README.md`).
- `dsh-agent-instructions` injects user-authored `AGENTS.md` chains. The agent reads them; nothing writes them as memory (`packages/context/agent-instructions/README.md`).
- The `ralph` tool states the gap outright: across fresh-agent rounds "the shared workspace is long-term memory,
  and only a bounded structured report crosses rounds" (`docs/tool-catalog.md`, `packages/workflow/tool-ralph`).

**Column: borderline, lean no.** The closest real mechanism is `dsh-tool-session-query`: five read-only model tools over the
durable session corpus, so raw-history recall across runs exists. But it fills only the store and recall rows. Extraction and
consolidation would both read "none", and "shipped host compositions do not mount it by default"
(`packages/session-query/tool-session-query/README.md`). It also overlaps the Hermes column's raw-history half.
If a column is added anyway, its story is "the log is the only memory".

### Named mechanisms

- `dsh-tool-session-query` (opt-in package): `session_search`, `session_event_search`, `session_trace`, `session_event_trace`, `session_event_read`.
- `session_search` searches prior sessions in the caller's workspace and returns the strongest matching event per session.
  Authorization is exact cwd equality between caller and target session; a caller without cwd can inspect only itself.
- Search filters by event surface: `current`, `shadowed` (compacted away), `log-only`. Compaction removes nothing from recall.
- `ctx.sessionQuery` service definition plus the SQLite full-text provider (`dsh-session-query-sqlite`).
- `dsh-session-reference` (`ctx.sessionReferenceResolver`): host-opt-in cross-session mentions as bounded read-only snapshots.
- Session persistence (`dsh-session-persistence-jsonl`, `-sqlite`): per-session append-only event log; resume and fork continue one session, they do not recall across sessions.

### Source anchors

- No memory event type: `docs/persistence-catalog.md` (complete generated event vocabulary).
- No memory tool: `docs/tool-catalog.md` (Tool Package Map).
- Search tools and cwd authorization: `packages/session-query/tool-session-query/README.md`, `packages/session-query/tool-session-query/src/index.ts`.
- Query service and surface classification: `docs/subsystems/session-query.md`, `packages/session-query/session-query/src/types.ts`.
- FTS provider: `packages/session-query/session-query-sqlite/src/index.ts`.
- Workspace invisibility to models: `docs/subsystems/workspace.md`, `packages/workspace/workspace/src/index.ts`.
- Same-session goals: `packages/goal/goal/README.md`, `packages/goal/goal/src/domain.ts`.
- Ralph filesystem-as-memory line: `docs/tool-catalog.md` (`ralph` entry).
- AGENTS.md injection: `packages/context/agent-instructions/README.md`.
- Cross-session mentions: `packages/context/session-reference/README.md`.

### Draft column gist (if added despite the lean-no)

- **Pros**: Nothing to extract or consolidate. The whole log stays searchable, compacted and log-only content included.
- **Cons**: No distilled store, so recall stays keyword-shaped over raw logs. The tool package is opt-in and off by default.
- **Why**: The append-only session log is the single source of truth, so recall reads the log instead of a second store.
- **How: store**: per-session durable event log (JSONL or SQLite) plus a full-text index. No memory files.
- **How: recall**: model-pulled search tools, authorized by exact workspace cwd match, strongest hit per session.
- **How: extraction**: none. **How: consolidation**: none.

### src/ update candidate

No. Section 9 `src/` already ships `SessionSearch` over an FTS session log, the same recall shape.

---

## Section 10 · System prompt assembly

### Verdict

**Yes.** A registry service with numeric order bands, scope shadowing, a cooperative assembly waterfall, strict variable
rendering, and tool schemas inside the same assembly. It contrasts with both existing columns: Claude Code's prompt builder
returns strings from one codebase, mini-swe renders templates once from config. dsh assembles from plugin registrations.

### Named mechanisms

- `dsh-system-prompt` package, service `ctx.systemPrompt`: `section()`, `context()`, `tools()`, `variable()`, `suppressRuntimeContext()`, `assemble()`.
- `PromptSection` with numeric `order`. Bands by convention: `-100` harness identity, `0` deployment persona, `100-199` tool guidance.
- `complete: true` section: after assembly it becomes the sole system prompt; two effective complete sections reject assembly.
- Scope shadowing via `dsh-scope`: an agent-scoped section or variable shadows a same-named global for that agent only.
- `system-prompt/assemble` waterfall event: scoped listeners mutate the assembly per caller. `system-prompt/change` emit fires on any registry change.
- `renderPrompt`: strict `{{variable}}` interpolation. An unknown reference, a valueless reference, or a malformed group throws. Fail loud beats a malformed prompt.
- Tool schemas are assembly members (`ToolProviderResult`). Config `toolOrder` fixes model-facing tool order with one
  `'<unlisted-tools>'` rest entry (`TOOL_ORDER_REST`); a misconfigured list rejects assembly before any model request.
- `PromptContext` dynamic contexts stay out of the system prompt. `RuntimeContextProjection` appends them as a durable
  user-role snapshot only when the rendered text changed or compaction shadowed the last one, with an explicit cleared marker.
- Assembly runs once per step: agent-loop calls `assembleContextFor(agent)` before each model request.

### Source anchors

- Registry, order bands, strict rendering, toolOrder: `packages/core/system-prompt/README.md`.
- Service and waterfall signatures: `docs/subsystems/system-prompt.md`, `packages/core/system-prompt/src/index.ts`.
- Snapshot-on-change projection and cleared marker: `packages/core/agent-loop/src/runtime-context.ts`.
- Per-step assembly point: `packages/core/agent-loop/README.md`, `docs/agent-lifecycle.md` (assemble waterfall inside each step).
- Cache framing (prefix-stable while text and order render identically): `packages/core/system-prompt/README.md` (KV Cache effect).

### Draft column gist

- **Pros**: Every prompt fact has one plugin owner. Strict rendering fails before a malformed prompt ships.
  Context snapshots append only on change, so the prefix stays cache-stable.
- **Cons**: A registry, scope layers, a waterfall, and order bands are heavy machinery. A bad tool order fails the first turn, not boot.
- **Why**: Plugins own their facts, so the prompt is assembled from registrations, never edited as one string.
- **How: assembly point**: a registry service plus a per-scope assembly waterfall; one `complete` section can override everything.
- **How: sections**: named sections in numeric order bands, scoped shadowing, strict `{{variables}}`, tool schemas carried in the same assembly.
- **How: when built**: once per step per agent scope. Dynamic context is split out as durable user-role snapshots appended only on change.

### src/ update candidate

Yes. Give `Section` a numeric `order`, sort at assembly, and fail loud on an unknown `{{variable}}` reference.

---

## Section 11 · Error recovery

### Verdict

**Yes.** Recovery is an event waterfall at the turn boundary, not a wrapper around the model call. Every retry is a durable
log event and reopens a fresh numbered turn over the same history. Both existing columns wrap the call (Claude Code
`withRetry`, mini-swe tenacity), so the contrast is direct.

### Named mechanisms

- `agent/request-error` waterfall: runs after the failed model step closes and before the turn closes.
  A handling listener returns `{ kind: 'retry' }`; the default leaves the failure terminal.
- `dsh-llm-retry`: does not wrap `ctx.llm.stream()`. One adapter call is one provider attempt;
  a retry opens a fresh numbered turn that reconstructs the request from durable surface history.
- Per-provider `retryPolicy`, captured at route registration. Normal mode: two retries on `EMPTY_RESPONSE`, `RATE_LIMIT`, `SERVER`,
  `TIMEOUT`, `TRANSPORT`, exponential backoff 500 ms to 10 s with 10 percent jitter. Always mode: unbounded, delegates downstream first.
- A valid `providerRetryAfterMs` at or below the cap replaces local backoff without jitter.
- Durable events `llm/retry` (scheduled, before the wait) and `llm/retry-started` (after the wait), correlated by `retryId`.
  Retry numbers continue only across an identical provider-plus-policy key.
- `LlmFailure`: provider-neutral codes. Canonical `CONTEXT_WINDOW_EXCEEDED` for overflow. An empty completion is the retryable error `EMPTY_RESPONSE`, not a silent success.
- Stream idle watchdog: adapters expose `streamIdleTimeoutMs` (five-minute default), arm it only while a chunk read is outstanding, and map expiry to `TIMEOUT`.
- Overflow recovery: `dsh-compaction-basic` listens on `agent/request-error` for canonical overflow only, prunes tool results, then summarizes,
  and returns retry only when the surface replacement generation advances. Its budget is separate from llm-retry's.
- Cancellation: `Agent.cancel(cause, { keepInbox })` with typed `AgentCancelCause` (`user`, `parent`, `hook`, `disposed`). The turn signal aborts
  active backoff, delegated recovery drains to quiescence, and `turn/end` records `{ kind: 'aborted' }` durably.
- Crash recovery: a persistence backend closes a crash-orphaned turn with synthetic `turn/end { kind: 'interrupted' }` and never truncates.
  Failed attempts commit no assistant message and no tool side effect, so no tool-pair repair is ever needed.
- Runtime diagnostics: `ctx.invariants` registry (`dsh-invariants`). Every package ships an `./invariant` companion; llm-retry's checks durable
  retry position, bounds, and retry numbers. Violations throw `InvariantError` with code `INVARIANT`.

### Source anchors

- Waterfall contract and `RequestErrorAction`: `docs/subsystems/core.md`, `packages/core/agent-loop/src/agent.ts`.
- Retry plugin, modes, backoff, durable events: `packages/llm/llm-retry/README.md`, `packages/llm/llm-retry/src/types.ts`.
- Failure codes, watchdog, empty-response rule, one-call-one-attempt: `docs/subsystems/llm-streaming.md` (adapter contract).
- Overflow path and retry-only-on-generation-advance: `docs/agent-lifecycle.md`, `packages/compaction/compaction-basic/src/index.ts`.
- Cancellation types and keepInbox: `docs/subsystems/core.md`, `packages/core/agent/src/runtime-types.ts`.
- Crash-orphaned turn close, no truncation: `docs/subsystems/persistence.md`; `TurnEndReasonMap` in `docs/subsystems/session.md`.
- Invariant registry and companions: `packages/runtime-diagnostics/invariants/README.md`, `packages/llm/llm-retry/src/invariant.ts`.

### Draft column gist

- **Pros**: Retries are durable log events, so a resumed session knows its recovery history. Failed attempts never enter the transcript.
- **Cons**: No fallback model. Always mode retries permanent failures without bound. A recovery listener that never settles blocks disposal.
- **Why**: The log is the source of truth, so recovery replays a fresh turn from durable history instead of patching an in-flight call.
- **How: retry**: `agent/request-error` waterfall with per-provider policy. A retry reopens a numbered turn; every retry is logged.
- **How: token handling**: canonical `CONTEXT_WINDOW_EXCEEDED` routes to prune-then-summarize compaction with its own budget.
- **How: model fallback**: none shipped. The retry turn reconstructs the same provider and model request.

### src/ update candidate

No. Section 11 `src/` teaches wrap-the-call retry; dsh's turn-boundary replay would replace `with_retry`, not extend it.
