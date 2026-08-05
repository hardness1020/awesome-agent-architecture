# ai-agent-book ch2 · Context Engineering vs sections 7, 8, 10

- Source: https://github.com/bojieli/ai-agent-book, `book/chapter2.md` (Chinese original, canonical).
- Date: 2026-08-05.
- Question: which mechanisms does ch2 teach that sections 7 (skills), 8 (context management), and 10 (system prompt) lack, which claims sharpen or contradict them,
  and which parts are source-worthy. Issue #16, part of #15.

## Per mechanism

- **KV cache economics.** A changed prefix token invalidates every cached token after it, so latency and cost jump.
  Heading: 「KV Cache 友好的上下文设计」 (KV-cache-friendly context design).
  Repo: §10 says stable before volatile and sets a cache breakpoint, but never states the cost model.
  Verdict: `enrich §10`. Add the failure economics (cache reads near one tenth of write cost, dynamic timestamps and tool reordering as anti-patterns).

- **Cache as architecture constraint.** A cache boundary splits the system prompt; each runtime condition before it doubles the cache-key variants (2^N).
  Heading: 「缓存作为架构约束」 (cache as an architecture constraint).
  Repo: §10 mentions Claude Code's explicit dynamic boundary in one line, without the variant math.
  Verdict: `enrich §10`. The 2^N argument is the missing why behind the boundary rule.

- **Frozen tool-result stubs.** The replacement string for a persisted tool result is frozen at first use, so restored sessions stay byte-identical with the cache.
  Heading: 「缓存作为架构约束」.
  Repo: §8's budget pass persists results and leaves a preview, but never says the stub must stay stable.
  Verdict: `enrich §8`. One sentence in the budget pass description, plus a failure-mode bullet.

- **Chat Template.** Structured messages become a model-specific token stream; hand-rolled `USER: ...` strings break trained formats and thinking retention.
  Heading: 「从 API 消息到模型 Token：Chat Template」.
  Repo: not covered.
  Verdict: `skip`. Serving-stack internals, below the harness layer this repo teaches.

- **Editable and composable KV cache.** Research direction: edit a cached field or splice precomputed cache blocks via RoPE relocation instead of recomputing.
  Heading: 「KV Cache 未必是一次性的」.
  Repo: not covered.
  Verdict: `skip`. Research stage, not a shipped harness mechanism.

- **Prompt content engineering.** Tone, XML plus Markdown structure, SOP-style flows over rule piles, business rules refined to executable precision.
  Heading: 「提示工程：优化系统提示词」 (prompt engineering).
  Repo: §10 covers assembly, not writing craft.
  Verdict: `skip`. Content authoring, not a harness mechanism. The ablation numbers are source-worthy for §10 (structure removal cut success over 30%).

- **Few-shot examples and prefix stability.** Examples live in the prefix, so per-request retrieval of "best" examples busts the cache; fix the set per task type.
  Heading: 「Few-shot 示例」.
  Repo: §10 has no example placement guidance.
  Verdict: `enrich §10`. It is a concrete instance of the volatile-prefix failure mode §10 already names.

- **Deferred tool loading (tool search).** The prefix keeps only tool names and one-liners; full schemas load on demand and append to the context end, cache-safe.
  Heading: 「工具定义的设计」 (tool definition design), closing paragraphs.
  Repo: §2 and §19 each have one failure-mode line saying defer schemas; §7 owns the pattern (progressive disclosure) but never mentions tools.
  Verdict: `enrich §7`. One paragraph: tools now use skills-style disclosure natively (OpenAI `tool_search` with `defer_loading`, Anthropic Tool Search, Codex BM25 search).

- **Context-layer prompt injection defense.** Separate instructions from data: source tags around external content, strict role structure, input filtering.
  Heading: 「提示注入：上下文安全的核心威胁」 (prompt injection).
  Repo: §3 covers execution-layer defense (permissions, sandbox). No section owns the context layer.
  Verdict: `candidate new section`. Instruction-vs-data separation is a harness mechanism with real system implementations, and no current section teaches it.

- **Skill supply-chain injection.** A third-party skill is external content loaded as instructions; a poisoned skill injects more directly than a poisoned webpage.
  Heading: same injection section, Skills paragraph.
  Repo: §7 failure modes cover routing and path traversal, not hostile skill content.
  Verdict: `enrich §7`. Add a failure-mode bullet: audit skill bodies like code before install.

- **Skills progressive disclosure.** Metadata catalog resident, body on demand, resources deeper still.
  Heading: 「动态提示词与 Agent Skills」.
  Repo: §7 covers the three levels, catalog, and evolution well.
  Verdict: `enrich §7`, small. Book adds: descriptions must read as routing conditions with counter-examples ("Use when / Don't use when"),
  catalog placement options (system prompt vs activation-tool description, per the open standard), and the not-zero-cost framing (one prefill, then cached).

- **Agent status bar.** The harness appends distilled runtime state (tool counts, TODO, time, env) at the context end, as a user-role message the model reads first.
  Heading: 「Agent 状态栏」 (agent status bar).
  Repo: split across §5 (todos), §9 (`<system-reminder>` injection), §10 (context messages for changing values). The update trade-off is nowhere:
  replace-each-turn keeps one clean state but invalidates tail cache; persistent append (Claude Code `<system-reminder>`) is cache-safe but accumulates stale state.
  Verdict: `enrich §10`. Add the replace-vs-append trade-off and the rule of maintaining state with code, not an LLM summarizer.

- **In-context learning is retrieval, not reasoning.** Attention finds facts but does not aggregate them; precomputed conclusions beat re-deriving from raw logs.
  Heading: 「上下文学习的内部机制：检索而非推理」.
  Repo: §8 motivates compaction only by window and cost limits.
  Verdict: `enrich §8`. Adds the second motivation: a distilled summary improves thinking quality even when the window is not full.

- **Context rot.** Retrieval precision decays as irrelevant content grows, well before overflow; the agent still runs but decides worse.
  Heading: 「为什么需要压缩」 (why compress), context rot paragraphs.
  Repo: §8 has one line ("old content competes with current task information") without the named concept.
  Verdict: `enrich §8`. Name it, and ground it with the Lost in the Middle citation.

- **Compression and cache interplay.** Compress between API calls; each edit invalidates cache after the edit point, so batch at a threshold instead of every turn.
  Heading: 「压缩与 KV Cache：看似矛盾，实则互补」.
  Repo: §8 orders its passes but never states their cache cost or why the trigger is a threshold.
  Verdict: `enrich §8`. The cache framing explains the trigger design §8 already documents.

- **Task-aware compression and retention priorities.** Summaries conditioned on the current query beat generic ones (about 3% vs 11% ratio in the book's runs);
  on compaction, keep architecture decisions, changed files, pass/fail status, and open TODOs; drop raw tool output first.
  Heading: 「实验 2-9」 and 「压缩策略的设计原则」.
  Repo: §8 has no retention priority list and its summarizer is not task-aware.
  Verdict: `enrich §8`. The priority list fits §8's failure modes; task-aware summarization fits the strategy row.

- **API-level context editing.** The server removes specified tool results from the prefix; zero local code, one cache rebuild, use only near overflow.
  Heading: 「生产级的分层压缩机制」, layer 3.
  Repo: §8's layered order (budget, snip, micro, collapse, auto, reactive) has no API-level layer.
  Verdict: `enrich §8`. One line in the layer list, with the near-overflow usage rule.

- **Isolation over compression.** Delegate noisy exploration to a subagent; only the conclusion enters the main context, and the main prefix stays cached.
  Heading: 「隔离优于压缩：子 Agent 上下文隔离」.
  Repo: §6 covers subagent context isolation.
  Verdict: `skip`. Already owned by §6; at most one cross-reference line in §8.

- **Attention sink and position bias.** The first token absorbs surplus attention; the middle of the context is under-attended.
  Heading: 「实验 2-2：注意力机制可视化」.
  Repo: not covered.
  Verdict: `skip`. Model internals; only the position-bias citation is useful, for §8.

- **API message roles and the core loop.** Four roles plus a `tools` field; the while loop over `stop_reason`.
  Heading: 「Agent 如何调用大模型」.
  Repo: §1 covers this.
  Verdict: `skip`. Already section 1's ground.

## Source-worthy citations

- Liu et al., "Lost in the Middle: How Language Models Use Long Contexts", TACL 2024. Grounds context rot in §8.
- Anthropic, "Equipping Agents for the Real World with Agent Skills", 2025. Engineering post behind §7's disclosure levels.
- Claude Code docs, "How Claude Code uses prompt caching" (code.claude.com/docs/en/prompt-caching). Grounds §10's boundary and §7's skill injection point.
- Agent Skills open standard, "How to add skills support to your agent" (agentskills.io). Catalog placement options for §7.
- OpenAI Responses API tool search docs (`defer_loading`); Claude Code MCP tool search docs; Codex CLI `search_tool` template. Deferred tool loading for §7.
- Li and Shi, "Distill, Don't Retrieve: Inference-Time Context Distillation for LLM Agent Reasoning", 2026. Status bar numbers, author's own benchmark.
- Li, "Models Take Notes at Prefill: KV Cache Can Be Editable and Composable", arXiv:2606.17107, 2026. Research frontier only, author's own paper.

## Claims vs the repo's text

No hard contradictions found. Four tensions worth resolving:

- The book calls sliding-window history a harmful anti-pattern (breaks cache, drops tool results, causes loops). §8 lists `snip` (drop stale middle turns) as a
  normal Claude Code pass. Not the same mechanism (budget persists results first), but §8 never states the cache cost of dropping middle turns.
- §10's table says dynamic parts stay memoized and the prompt is rebuilt per turn. The book's rule is that the prefix must stay byte-stable once set.
  The boundary reconciles them, but §10 does not say that conditions placed before the boundary multiply cache keys.
- §7's table says "A `Skill` tool call injects the body". The book, citing the Claude Code prompt caching doc, says the body lands as a user message at the call
  position. Both can hold; §7 could name the injected role.
- The book measured that models trust injected state summaries unconditionally and never re-verify them. §8's failure modes cover lost detail, not false trust
  in a wrong summary. Same risk applies to §9's recalled memory.
