# ai-agent-book ch5 · Coding Agent vs the core harness chain

- Source: https://github.com/bojieli/ai-agent-book · `book/chapter5.md` (Chinese original, canonical).
- Date: 2026-08-05.
- Question: this repo already studies Claude Code end to end (sections 1 to 5, 11, 15).
  What does the book's coding-agent chapter add beyond those per-system studies?

Verdict key: `enrich §N` (fold into an existing section), `candidate new section`, `skip` (already covered, or out of harness scope).

## Per mechanism

### Coding agent core

- **Seven-tool reference set.** Interpreter, bash, read, write, edit, glob, grep as the canonical minimal toolbox.
  Heading: Coding 是 Agent 的基础能力. Covered: §2 already contrasts a full catalog with a single bash tool.
  Verdict: skip. Framing, not a mechanism the repo lacks.
- **Filesystem as agent hub.** Markdown memory files plus a persistent workspace instead of a vector store.
  Heading: 从 Manus 到 OpenClaw. Covered: §9 memory owns file-based memory.
  Verdict: skip. Outside this chain and already owned by §9.
- **Sessionless state survival.** Workspace files persist across messages. Process state (cwd, env vars, background tasks) is serialized before idle teardown and rebuilt on wake.
  Heading: Sessionless 设计. Covered: no section owns cross-message process-state rebuild.
  Verdict: skip. Single-system OpenClaw product design with thin verifiable detail. Revisit only if the repo studies session resume.

### Security

- **Lethal trifecta plus memory.** Threat model: private data access, untrusted content, external comms. Persistent memory amplifies an attack across sessions.
  Heading: Coding Agent 的安全. Covered: §3 says trusting the model is not a boundary, but names no threat model.
  Verdict: enrich §3. Gives the gate a citable threat model and a memory-poisoning axis.
- **Sandbox egress, mounts, quotas.** Default-deny network with an allowlist proxy. Read-only source mounts, no credential mounts, one writable workspace.
  Quotas and wall-clock timeouts return structured errors to the model instead of silent kills.
  Heading: Coding Agent 的安全 (隔离兜底). Covered: §3 has a sandbox row but no egress or mount policy.
  Verdict: enrich §3. Concrete sandbox dimensions the per-system table lacks.
- **Semantic command parsing.** Parse flag consumption rules to catch `find -exec rm`, `$(echo rm) -rf /`, `curl -o /etc/crontab`.
  Heading: Coding Agent 的安全. Covered: §3 failure modes name pattern-match bypass without a mitigation mechanism.
  Verdict: enrich §3. Supplies the mitigation the failure bullet already asks for.
- **Speculative permission checks.** Show a no-side-effect progress hint while the check runs in the background. Swap to a confirm prompt only when it cannot decide fast.
  Heading: Coding Agent 的安全. Covered: nowhere. §3's gate is synchronous.
  Verdict: enrich §3. A latency design for the ask path.
- **Process constraints beside result checks.** Block destructive shortcuts (delete and rebuild) even when the end result would pass verification.
  Heading: Harness 工程在 Coding Agent 中的实践. Covered: §3 gates destructive calls, §21 verifies results. The result-versus-path distinction is unstated.
  Verdict: enrich §3. One line: constrain actions, not only outcomes.
- **Principal loyalty rules.** In multi-party settings the owner's instructions outrank all external content.
  Refuse without enumerating what is protected. Resist repeated pressure.
  Heading: Agent 为谁效忠. Covered: §10 assembles system rules but has no multi-party trust framing.
  Verdict: enrich §10. Names a prompt-layer defense the repo lacks. The source is the author's own eval, flag it as such.
- **Data-layer invariant enforcement.** Treat AI-written app code as untrusted. Enforce per-entity permission rules from a human-reviewed schema below it, on every write.
  Heading: 当 AI 写的代码本身不可信. Covered: no.
  Verdict: skip. Sits below the harness, and the source is the author's unpublished paper.

### Workflow and harness framing

- **Staged engineering workflow.** Document, clarify, design doc, implement and test, sync docs. Real agents trim it per task.
  Heading: Coding Agent 的整体流程. Covered: §5 owns the harness part (plan mode, todos). The rest is prompt-level policy.
  Verdict: skip. The book itself says production agents cut it down. Policy, not mechanism.
- **Model-harness boundary framing.** When to stop reading and start editing is a model-learned policy that travels across harnesses.
  Scaffold thickness should track model strength. The same scaffold gives opposite conclusions on different models.
  Heading: Coding Agent 的整体流程, plus the 实验 5-2 discussion. Covered: §0 says re-evaluate layers per model, without these sharper claims.
  Verdict: enrich §0. Testable framing for the thesis.
- **Task quadrant.** Task clarity times verification automation. Coding agents are mature because SWE infrastructure (tests, types, git) is a ready-made harness.
  Heading: Harness 工程在 Coding Agent 中的实践. Covered: §0 thesis and §21 verification, but not the quadrant frame.
  Verdict: enrich §0. One table that explains where agents work and where they fail.

### Failure and recovery

- **Four-layer failure taxonomy.** API, tool, context, control flow. Classify retryability first, count second. Keep an error-to-strategy map.
  Heading: 故障与错误恢复. Covered: §11 handles the API layer well but has no cross-layer taxonomy.
  Verdict: enrich §11. Ready-made structure for the section opening.
- **No-progress loop detection.** Fingerprint tool name plus args. Repeated fingerprints signal a stuck loop. Per-recovery-path failure counters feed the breakers.
  Heading: 故障与错误恢复. Covered: §1 has only a max-step backstop.
  Verdict: enrich §11. A named detection mechanism, cheap to implement.
- **Liveness and integrity monitoring.** An idle watchdog kills silently stalled streams, since connect timeouts miss transport stalls.
  Missing `tool_result` pairs are repaired before injection.
  Product mode repairs with placeholders. Training-data mode refuses, because synthetic placeholders would pollute the data.
  Heading: 故障与错误恢复. Covered: §1 names the lost-result invariant. No watchdog or repair mechanism anywhere.
  Verdict: enrich §11. The product-versus-training dual standard is a distinctive finding.
- **Graded recovery with error quarantine.** Silent retry, then degrade and continue, then surface with the attempts listed.
  Hold intermediate errors from consumers until recovery fails.
  Background calls get no retries, so they cannot starve the main loop's quota.
  Heading: 故障与错误恢复. Covered: §11 has bounded retry and fallback but no transparency grading or quarantine.
  Verdict: enrich §11. Organizes what §11 already has and adds two rules.
- **Death spiral defenses and empirical thresholds.** On error paths, disable side-effect logic that calls the model again. A recursion depth counter breaks residual chains.
  Breaker thresholds come from production data, not intuition (see citations).
  Heading: 故障与错误恢复. Covered: §11 failure modes name the stop-hook repeat and bounded paths. The threshold provenance is new.
  Verdict: enrich §11. Adds the why behind the bounds §11 already prescribes.

### Implementation tricks

- **Streaming tool start and cascade abort.** Run a call as soon as its args parse, overlapping with generation of later calls.
  A failure aborts only dependent calls in the same batch, never independent calls or the parent operation.
  Heading: Coding Agent 的实现技巧. Covered: §2 batches safe calls. No early start, no failure-scope rule.
  Verdict: enrich §2. Two concrete rules for the parallel-calls row.
- **Persistent shell session by default.** One shared terminal keeps cwd, env vars, and venv activation. Isolated shells stay available for parallel work.
  Heading: Coding Agent 的实现技巧. Covered: no section states the shell-state dimension.
  Verdict: enrich §2. Also a live contradiction with Claude Code, see below.
- **Lint-on-write feedback.** The tool layer runs a linter after every write and appends diagnostics to the tool result.
  Heading: Coding Agent 的实现技巧. Covered: §4 PostToolUse can observe results. The feed-diagnostics-back pattern is unstated.
  Verdict: enrich §4. The canonical PostToolUse example.
- **Ranged reads and head-tail truncation.** Line-number prefixes, ranged reads, truncate long output to head and tail with the full copy persisted.
  Heading: Coding Agent 的实现技巧. Covered: §2 failure modes already prescribe cap, persist, preview.
  Verdict: skip. Already present in §2. The remainder is small detail.

### Coding tool design

- **Four-way code search comparison.** Grep, glob, embedding index, LSP symbols. Claude Code skips the index (agentic grep), Cursor pays for it (semantic recall).
  Heading: Coding Agent 中的搜索工具. Covered: §2's discovery row covers schema discovery only.
- **Five-way edit scheme comparison.** Diff plus apply model, old-new string, line numbers, vim-like commands, anchor (start plus end) matching.
  Cursor's trained fast-apply model with speculative decoding versus Claude Code's exact string replace.
  Heading: Coding Agent 中的文件编辑工具. Covered: nowhere.
- Verdict for both: candidate new section (coding search and edit tools). Two full comparisons that outgrow §2's registry focus, with material for a Cursor column.

### Meta-capability part

- **Checklist params with server-side truth.** Optional `expected_*` params force a pre-call policy check. The handler reads only database truth and logs mismatches.
  Heading: 代码作为业务规则的约束. Covered: §2 defines schemas, §3 gates calls. Neither covers tool interfaces that distrust model-reported facts.
  Verdict: enrich §2. A tool-design pattern: the last gate must stand on data the model cannot forge.
- **Proposer-reviewer iteration.** Split generation and review into two agents. The reviewer sees rendered output the proposer cannot, and returns structured feedback.
  Heading: 代码驱动的多媒体生成. Covered: §21 maker-checker split, §6 subagents.
  Verdict: skip. Same mechanism, applied to slides and video.
- **Meta-capability applications.** Code as thinking tool, system adapter, generative UI, SQL artifacts, agent bootstrapping, doctor self-repair.
  Headings: 代码：通用 Agent 的元能力 and the sections after it. Covered: application content, not harness mechanisms.
  Verdict: skip. Outside the harness chain this repo studies.

## Source-worthy citations

- Simon Willison's lethal trifecta: private data access, untrusted content, external comms. The book adds persistent memory as a fourth, amplifying dimension.
- Footnote ch5-3: the failure taxonomy comes from source study of production agents, Claude Code named. The book warns the implementation evolves fast.
- Production numbers behind the compaction breaker: one session failed the same recovery path 3000+ times, and such loops wasted about 250k API calls per day.
  The 3-strike bound came from that data.
- τ-bench (tau-bench): customer-service benchmark grounding the checklist-params pattern.
- Li and Shi, Whose Side Is Your Agent On? Multi-Party Principal Loyalty in LLM Agents, arXiv:2606.30383. Author self-citation for the loyalty spectrum.
- Li, The Application Layer Is No Longer Trusted, 2026, unpublished. Author self-citation for data-layer enforcement.
- Cursor fast-apply: skeleton diff rewritten by a trained apply model with speculative decoding, on the order of 1000 tokens per second.
- A2UI versus AG-UI: A2UI is a declarative UI payload, AG-UI is an event transport that can carry it. The book flags conflating them as a common error.
- Anthropic long-task pattern: an initializer agent decomposes work into a task list, an executor agent advances it and leaves artifacts for the next round (§5, §12 orbit).
- LangChain result: harness-only optimization lifted benchmark scores, with an agent analyzing failure traces to improve the harness (§21 improvement-loop orbit).

## Contradictions and tensions

- Shell state. The book recommends one persistent terminal session as the default execution mode.
  Claude Code resets shell state between Bash calls and instructs absolute paths instead. Flag both designs if §2 gains this dimension.
- The book's staged workflow is self-flagged as an ideal. It states that Claude Code and OpenClaw run reactive loops and trim the stages.
  No conflict with §5, quote it as the book's own caveat.
- The seven-tool set separates Code Interpreter from Bash, then immediately notes real systems merge them. Presentation choice, not a factual conflict.
- Footnote ch5-3 warns its Claude Code findings track a fast-moving implementation. Treat the production numbers as period evidence, not current behavior.
