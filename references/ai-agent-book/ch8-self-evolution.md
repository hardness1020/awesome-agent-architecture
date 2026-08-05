# Book ch8 · Self-Evolution vs sections 7, 18, 21

- Source: bojieli/ai-agent-book, `book/chapter8.md` (Agent 的持续进化), Chinese original, read in full.
- Date: 2026-08-05. Ticket: issue #21, part of #15.
- Question: is self-evolution a distinct harness mechanism this repo misses, or a recombination of skills, autonomy, and loop engineering it already teaches?

## Mechanisms

1. **Trajectory verification.** Three verifier layers turn a run into a learning signal: outcome truth, process rules, rubric quality, each with evidence.
   Book: 从运行轨迹中获得学习信号. Repo: §21 has one separate checker with a fixed rubric; §20 grades offline.
   Verdict: enrich §21. The outcome, process, quality split and per-dimension evidence make §21's "is it actually done" concrete.

2. **Carrier selection.** The representation of a capability picks where a learned change lands: knowledge doc, prompt or skill, program, or weights.
   Book: Agent 持续进化的四种方法 and 从问题定位到经验沉淀. Repo: §21's improvement loop names "config, skills, or model" with no decision rule.
   Verdict: enrich §21. The rule (smallest, most verifiable, most reversible target first) is the missing routing step of the improvement loop.

3. **Experience knowledge base.** Cross-trajectory distillation into retrievable docs, with immutable trajectories below and support thresholds above.
   Book: 将经验沉淀为知识. Repo: §9 teaches the minimum memory loop; production depth lives in learn-agent-memory.
   Verdict: skip. Owned by §9 and the learn-agent-memory repo, not by §7, §18, or §21.

4. **System prompt learning.** Repeated failures become a minimal prompt diff, scoped, checked against boundary cases and a holdout set, then canaried.
   Book: 将经验写成指令. Repo: §21 says "propose a bounded edit, validate against a regression set" in one line.
   Verdict: enrich §21. Trigger evidence, minimal diff, and the canary gate give that line its production shape.

5. **Skill learning.** Run evidence triggers generating or patching a skill; search the store first, patch over create, keep sources and pitfalls in the body.
   Book: 将经验写成指令 (Skill 学习). Repo: §7 has `WriteSkill` growth and curator decay.
   Verdict: enrich §7. §7 teaches the write; the book adds when to write (support threshold) and the candidate step before the catalog.

6. **Workflow compilation.** A first exploration compiles into a parameterized program with pre, post, and final state checks, replayed without the model.
   Book: 将经验写成程序 (browser workflow lifecycle, PreAct). Repo: not covered; §7 skills stay instructions, §2 tools are hand-written.
   Verdict: candidate new section. A full lifecycle (capture, parameterize, validate on reset, replay, invalidate) with no home in any section.

7. **Tool creation.** A capability gap triggers the agent to find a library, wrap it as a tool, and validate it into the capability library.
   Book: 将经验写成程序 (Alita). Repo: not covered; §2's registry is fixed at startup.
   Verdict: candidate new section. Same section as 6; both share the candidate to validated capability lifecycle.

8. **Harness self-modification.** A change contract (evidence, root cause, predicted impact) gates a minimal patch to the agent's own code, then canary.
   Book: 将经验写成程序, closing part (AHE, Self-Harness). Repo: §21 names the self-editing loop and its escaped-gates failure mode in three lines.
   Verdict: enrich §21. The change contract and the bounded candidate space are the auditable form of what §21 already sketches.

9. **Meta-optimization ladder.** Search scales widen from one rule to context, workflow, harness code, then optimizer code; prefer the smallest scale.
   Book: 从更新产物到更新"更新方法" (ACE, MCE, AFlow, Meta-Harness). Repo: §21 cites the same Weng post and says "the loop structure becomes a search space".
   Verdict: enrich §21. The ladder and the prefer-smallest rule turn that sentence into a usable decision.

10. **Dual-loop separation.** The online loop only executes and records evidence; an offline loop aggregates, diagnoses, generates candidates, and releases.
    Book: 构建可长期运行的持续进化闭环 (Voyager). Repo: §21's four stacked loops do not split online from offline or version candidates.
    Verdict: enrich §21. The split is why one lucky run or one injected page cannot rewrite the production agent.

11. **Evolution metrics split.** Harness updating (good candidates) and harness benefit (activation, adherence, held-out gain) are measured separately.
    Book: 验证、发布与回滚 (Lin et al.). Repo: §20 grades end to end only; §21 reads one pass rate.
    Verdict: enrich §21. Without the split, a correct skill that never loads reads as a failed update.

12. **Safety boundaries.** Untrusted output must not become experience; candidates stay isolated from formal capabilities; gates are not self-modifiable.
    Book: 持续进化的安全边界. Repo: §21 has the trusted-root failure mode; §3 gates the write.
    Verdict: enrich §7. The missing piece is §7-shaped: a prompt injection distilled into a skill persists across sessions.

13. **Sleep-time consolidation.** A gated background cycle: trigger, orient, gather and merge, validate and approve, prune and index.
    Book: 睡眠学习：整合、遗忘与能力保鲜 (Claude Code memory, Hermes curator). Repo: §7 names the curator and its signals; §9 names cleanup.
    Verdict: enrich §7. The five-step cycle gives §7's curator paragraph a concrete shape, including snapshot and rollback.

14. **Verifiable-loop boundary.** On open-ended tasks the loop drifts: familiar implementations, noise read as findings, survivor-only evidence.
    Book: 可验证闭环的边界. Repo: §21's failure modes cover rubber-stamp rubrics, not proxy-goal drift.
    Verdict: enrich §21. One failure-mode bullet: the proxy metric passes while the real goal drifts; keep negative results.

15. **Parameter updates.** Evaluated production trajectories become SFT, preference, or RL data; regression covers forgetting and safety.
    Book: 将经验写入参数. Repo: not covered anywhere.
    Verdict: skip. Model training sits outside this repo's harness thesis.

## Answer

Self-evolution is mostly a recombination the repo already teaches, plus one genuine gap.

- The chapter's closed loop is §21's verification and improvement loops run over §7's growing and decaying skill store, with §20 eval, §9 memory, and §3 gates.
- What the repo holds in single lines, the chapter develops in depth: the candidate lifecycle (capture, distill, candidate, validate, promote, roll back).
  That is enrich work, mostly §21, partly §7.
- One mechanism has no home in any section: compiling trajectories into parameterized, state-checked programs and validated tools, replayed without the model.
  That is the "tool user to tool creator" move and the one candidate new section (items 6 and 7).
- §18 is not part of the story. The book's offline learner is a scheduled background process (§13, §14 territory), not a self-organizing worker claiming tasks.
  No ch8 mechanism lands in §18.

## Source-worthy citations

- Voyager, arXiv:2305.16291. Curriculum, skill library, and environment verification as one closed loop; skills transfer to new worlds.
- PreAct, arXiv:2606.17929. Trajectory to workflow compilation, 8.5 to 13x replay speedup, pre, post, and pre-save validation.
- Alita, arXiv:2505.20286. Capability-gap-triggered tool creation with validation before library entry.
- Karpathy, "system prompt learning", X, May 11 2025. Editing words instead of weights as a third learning paradigm.
- ACE, arXiv:2510.04618. Incremental context items with stable ids instead of full rewrites.
- GEPA, arXiv:2507.19457; DSPy, arXiv:2310.03714; OPRO, arXiv:2309.03409. Offline prompt optimization routes.
- Lin et al., arXiv:2605.30621. Harness updating vs harness benefit, separated by model swaps.
- AHE, arXiv:2604.25850; Self-Harness, arXiv:2606.09498. Change contracts and bounded candidate spaces for self-modification.
- Anthropic Skill Creator, github.com/anthropics/skills. Draft, test, evaluate, revise loop for skill generation.
- Hermes curator docs (already in §7 sources). Snapshot before change, deterministic pruning, rollback.

## Contradictions

- §7's demo promotes a skill on first success: the agent saves it and the next scan catalogs it, gated only by permission.
  Ch8 requires cross-trajectory support (at least two non-failed trajectories) and independent validation before formal capability. Real tension for an enrich pass.
- §7's staleness signal counts loads as use. Ch8's activation vs adherence split shows a loaded skill may still be ignored, so load counts overstate learning.
- No direct factual conflicts found; §21 already cites the same Weng post the book builds on, so an enrich pass should dedupe rather than re-cite.
