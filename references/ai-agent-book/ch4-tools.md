# ai-agent-book ch4 (Tools) vs sections 2, 13, 14, 19

- Source: [ai-agent-book](https://github.com/bojieli/ai-agent-book) `book/chapter4.md`, Chinese original, canonical.
- Date: 2026-08-05.
- Question: which ch4 mechanisms are missing from sections 2 (tool runtime), 13 (background execution),
  14 (scheduling), and 19 (MCP/plugins/channels); which sharpen existing text; which are source-worthy.

## Mechanisms

Each entry: name, one-line description, book heading, current coverage, verdict.

- **Five-tool taxonomy**
  - Groups tools as perception, execution, collaboration, event-trigger, user-communication, by call direction and target.
  - Book heading: 工具的分类.
  - Coverage: no section groups tools; §2 treats the catalog as flat.
  - Verdict: `enrich §2`. One framing sentence maps the catalog and names where §13, §14, §19 pick up.

- **Dedicated tool vs Skill plus general executor**
  - A three-axis choice (parameter complexity, change rate, model strength) between a schema tool and a Skill doc run by bash.
  - Book heading: 能力表达形式的选择.
  - Coverage: §7 owns Skills; the decision framework is nowhere.
  - Verdict: `skip`. §7 territory, outside this ticket's sections.

- **Tool granularity**
  - Merge tools with similar function and overlapping use (one `read_document` with a type param); keep split when params diverge.
  - Book heading: 工具粒度的权衡.
  - Coverage: not covered; §2's per-system contrast (full catalog vs one bash tool) shows only the extremes.
  - Verdict: `enrich §2`. Granularity is the missing middle between those extremes.

- **Generality over specialization**
  - Prefer a general tool (`code_interpreter`) over many specialized ones, unless safety or permissions argue otherwise.
  - Book heading: 工具的通用性设计.
  - Coverage: embodied in §2's mini-swe-agent column (one bash tool) and its stated trade-offs.
  - Verdict: `skip`. Already implicit in the per-system contrast.

- **Tool description craft**
  - Descriptions state when to use, boundaries and non-goals, concrete param examples, return shape, and cost. Add 1 to 5 real call examples.
  - Book heading: 工具描述的艺术.
  - Coverage: §2 mentions `description` only as an advertised field.
  - Verdict: `enrich §2`. Wrong-tool selection is usually a description bug; fits a failure-mode bullet with its mitigation.

- **Parameter fidelity**
  - The harness must not silently rewrite tool inputs (quote normalization) or inject extra args; the model cannot diagnose the drift.
  - Book heading: 参数传递的保真性.
  - Coverage: not covered anywhere.
  - Verdict: `enrich §2`. Clean failure-mode bullet: silent transformation makes edits fail with no visible cause.

- **Code orchestration of tool calls**
  - The model writes a script that chains tools; intermediate data stays in the executor, only the summary returns.
  - Book heading: 工具设计的演进.
  - Coverage: not covered.
  - Verdict: `skip`. The book defers the mechanism to its ch5; revisit with a ch5 ticket.

- **MCP protocol basics**
  - Client-server tool interop: JSON Schema definitions, stdio and Streamable HTTP, and three primitives (tools, resources, prompts).
  - Book heading: 工具生态：MCP 与工具选择的挑战.
  - Coverage: §19 covers the protocol and the 2026-07-28 stateless revision in more depth than the book.
  - Verdict: `enrich §19`, small. §19 shows only tools; one line naming resources and prompts completes the primitive set.

- **MCP context overhead and deferred exposure**
  - Five servers can cost tens of thousands of tokens up front; index names, load definitions on demand; adopting MCP and exposing all schemas are separate decisions.
  - Book heading: MCP 工具的上下文开销管理 (under 工具生态).
  - Coverage: §19's tool-list-bloat failure mode and §2's discovery row already state defer loading, without numbers or the two-decisions point.
  - Verdict: `enrich §19`. The separation of interop from exposure sharpens the bloat mitigation.

- **MCP trust model**
  - Description poisoning (injected instructions in tool descriptions), tool shadowing across servers, hijacked updates, credential scope.
  - Book heading: MCP 的信任模型与安全风险 (under 工具生态).
  - Coverage: §19 has only the lying `readOnlyHint` failure mode.
  - Verdict: `enrich §19`. Poisoning and shadowing are missing failure modes with concrete mitigations (audit descriptions, pin versions, least-privilege credentials).

- **Perception tool interface rules**
  - Search returns paged candidate lists with a cursor; reads take offset and limit; truncation is explicit, never silent.
  - Book heading: 感知工具.
  - Coverage: §2's oversized-results bullet covers cap, persist, preview; pagination and the silent-truncation warning are missing.
  - Verdict: `enrich §2`, light. Fold pagination and explicit truncation into the existing bullet.

- **Multimodal perception strategies**
  - Native multimodal input vs extract-to-text vs analysis-as-tool, chosen per content type.
  - Book heading: 多模态感知.
  - Coverage: not covered.
  - Verdict: `skip`. Model capability topic, not a harness mechanism.

- **Execution safety layers and sandbox ladder**
  - Input validation, blacklists, then OS sandbox, container, microVM, resource quotas; venv is not a sandbox.
  - Book heading: 执行工具.
  - Coverage: §3 (permission and sandbox) owns this ground.
  - Verdict: `skip`. Outside this ticket's sections.

- **Proposer-Reviewer and Sidecar review**
  - A second model pre-approves irreversible calls or verifies results in another modality; a parallel lightweight classifier gates each call on structured data only.
  - Book headings: 提议者-审核者 and Sidecar 机制 (under 执行工具).
  - Coverage: not covered; §3 gates with rules and a human ask, not a second model.
  - Verdict: `skip`. Fits §3 or §18 if ever revisited, outside this ticket's sections.

- **Auto-verification feedback loop**
  - A write tool runs the linter and returns structured errors in the same `tool_result`.
  - Book heading: 自动验证与反馈闭环 (under 执行工具).
  - Coverage: §4 hooks (PostToolUse) own this pattern.
  - Verdict: `skip`. §4 territory.

- **Long-output truncation and persistence**
  - Keep head and tail, save the full output to a file, return the path.
  - Book heading: 长输出的截断与持久化 (under 执行工具).
  - Coverage: §2's oversized-results failure bullet says exactly this.
  - Verdict: `skip`. Already covered.

- **Idempotency and cancel semantics**
  - After a timeout or cancel, did the side effect happen? Idempotency keys, query-before-mutate, and two-phase precheck-confirm for unrepeatable ops.
  - Book heading: 幂等性与取消语义 (under 执行工具).
  - Coverage: §13 has kill paths but never asks whether a killed call's side effect landed.
  - Verdict: `enrich §13`. Failure-mode bullet: blind retry after timeout double-fires a real-world action.

- **Collaboration primitives**
  - Spawn, message, cancel, list agents; sync, async, streaming, and multi-turn forms.
  - Book heading: 协作工具.
  - Coverage: §6, §12, and §16 own these mechanisms.
  - Verdict: `skip`. Outside this ticket's sections.

- **HITL approval with timeout and defaults**
  - Human approval requests carry a timeout, a default action, and a priority channel.
  - Book heading: 人工介入的艺术 (under 协作工具).
  - Coverage: §3 and §18 own approval flow.
  - Verdict: `skip`. Outside this ticket's sections.

- **Event-driven async architecture with urgency triage**
  - All inputs become one event stream consumed at loop-boundary safe points.
    Urgency picks the strategy: cancel (make a safe point now), queue (batch at the next one), or parallel (a side loop).
    A light LLM routes events. Interrupting an in-flight tool needs a placeholder `tool_result` to keep the sync trace legal.
  - Book headings: 事件驱动的异步 Agent, 事件处理机制, 工程实现：如何让同步模型支持异步打断.
  - Coverage: partial and scattered. §13, §14, and §16 each drain a queue between turns, and §19 gates inbound channel events.
    No section teaches cancellation, urgency triage, structured event modeling, or interrupt placeholders.
  - Verdict: `candidate new section`. The safe-point rule already implicit in four sections deserves a named home, and interrupts fit nowhere today.

- **Async tool interface naming**
  - Name and describe slow tools as start operations (`initiate_*` returns a task id); completion arrives as a separate event.
  - Book heading: 适合现有模型的异步工具接口.
  - Coverage: §13's `backgroundable` wrapper implements exactly this; the naming-and-description principle is unstated.
  - Verdict: `enrich §13`, light. One sentence names the principle the code already follows.

- **Batched-event attention dilution**
  - Given several queued events at once, models attend to the last one; number each event and append a summary line.
  - Book heading: 队列式处理中的注意力分散问题.
  - Coverage: §13's `drain_into` folds many notifications into one turn with no markers.
  - Verdict: `enrich §13`. Failure-mode bullet with the marker-plus-summary mitigation.

- **Heartbeat and the limits of time-driven wakeups**
  - A periodic wake with judgment (avoid alert fatigue) covers sources that cannot push; cron and heartbeat still miss events between ticks.
  - Book heading: 从 OpenClaw 看事件驱动的现实需求.
  - Coverage: §14 covers cron and one-shot triggers; the heartbeat pattern and the poll-to-push trade-off are missing.
  - Verdict: `enrich §14`. Heartbeat is a third trigger type, and the trade-off motivates §19's channels.

- **External event channels**
  - Push external events (mail, callbacks, IM) to the agent instead of polling; second-level latency.
  - Book heading: 事件触发工具.
  - Coverage: §19's channels cover inbound push with gating; §13 covers background task monitoring.
  - Verdict: `skip`. Already covered; the motivation rides the §14 heartbeat note.

- **User communication tools and multi-channel recall**
  - Sending to the user is an explicit tool call; the agent picks the channel by urgency, and notifications recall attention.
  - Book heading: 用户沟通工具.
  - Coverage: §14's `deliver` routes output to a named channel with `[SILENT]`; §19's channels are two-way.
  - Verdict: `skip`. Core routing is covered; channel choice by urgency is product policy.

- **Virtual identity and isolated environments**
  - The agent gets its own accounts, virtual computer or phone, VNC-based HITL login, and a shared volume for data exchange by path.
  - Book heading: 虚拟身份与隔离执行环境.
  - Coverage: not covered; §15 is git worktrees, §3 is code sandboxing.
  - Verdict: `skip`. Product infrastructure, weak fit for the harness sections.

- **Proactive tool discovery**
  - The agent declares a capability gap in natural language; the system matches server-then-tool hierarchically and injects the schema (MCP-Zero, tool-search tools).
  - Book heading: 主动工具发现.
  - Coverage: §2's discovery row has Claude Code's name-first, load-on-request search; need declaration and two-layer routing are missing.
  - Verdict: `enrich §2`. Sharpens the discovery row and adds a strong source (MCP-Zero).

- **Cache-safe dynamic loading**
  - Append a discovered schema at the context end once; it stays at that position as history, so the prefix cache keeps hitting.
  - Book heading: 主动工具发现 (动态加载与 KV Cache).
  - Coverage: §2 defers schemas but never states the placement rule; §8 owns KV cache generally.
  - Verdict: `enrich §2`, light. One line on why deferred schemas append instead of editing the prefix.

- **Skills as progressive-disclosure discovery**
  - A thin name-and-description catalog; the model greps and reads deeper layers on demand, no embedding index.
  - Book heading: Skills：把工具发现变成按需查阅.
  - Coverage: §7 owns Skills and progressive disclosure.
  - Verdict: `skip`. §7 territory.

- **Continuous-time agents and composable KV cache**
  - Research previews: inject events into an unbroken thinking stream; precompile skill KV blocks for reuse.
  - Book headings: 深层矛盾与未来方向, Skills 一节末尾.
  - Coverage: not covered.
  - Verdict: `skip`. Unpublished or single-source author research, not yet citable ground.

## Source-worthy citations

- MCP-Zero: Fei et al., "MCP-Zero: Active Tool Discovery for Autonomous LLM Agents", arXiv:2506.01056. For §2 discovery.
- Anthropic Tool Search Tool (Claude API) and the Opus 4 accuracy claim (49% to 74%). Verify against Anthropic docs before citing.
- OpenAI Responses API `defer_loading` and `tool_search_output`; Codex CLI BM25 `tool_search`. For §2 discovery context.
- Cursor A/B on file-indexed MCP tool descriptions (46.9% token cut). The book gives no link; find Cursor's writeup before use.
- Pi coding agent "no MCP" philosophy and the `pi-mcp-adapter` proxy-tool pattern. For §19's deferred-exposure point.
- MCP docs: "Build an MCP server with Agent Skills" and the Skills over MCP working group. For §19 or §7.
- MCP specification 2026-07-28: already a §19 source; the book's reading matches §19 (stateless wire, subscriptions, SSE deprecated).

## Contradictions

- No hard contradictions with the four sections. Points to watch:
- Interrupt placeholders vs §13's pairing rule. The book pairs a synthetic `tool_result` with the in-flight `tool_use_id` at interrupt time;
  §13 forbids reusing the old id for the late real completion. Complementary: the placeholder closes the pair, the real result still arrives
  as a new notification. State both together if §13 grows.
- The book says Claude Code defers MCP tool loading by default via `tool_reference` blocks; §19 lists deferral as a mitigation, not a default.
  Verify default-vs-optional before hardening either claim.
- The book's benchmark numbers (72% to 90% with call examples, 46.9%, 55K tokens, 98%, 49% to 74%) carry no in-chapter citations except MCP-Zero. Treat them as leads, not sources.
