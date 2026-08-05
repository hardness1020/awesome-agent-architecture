# Book ch10 · Multi-Agent vs sections 16, 17, 18, 22

- Source: [ai-agent-book](https://github.com/bojieli/ai-agent-book), `book/chapter10.md` (多 Agent 协作), Chinese original.
- Date: 2026-08-05.
- Question: which ch10 mechanisms should enrich §16 (coordination), §17 (protocols), §18 (autonomy), §22 (graph engineering), and which are new or out of scope.

## Mechanisms

1. **Shared vs isolated context.** A successor agent inherits the full trajectory, or each agent keeps its own context and communicates explicitly.
   Book: 「维度一：上下文是否共享」.
   Coverage: the repo assumes isolation (§6 fresh subagent context, §16 inboxes). The shared branch and the selection checklist are absent.
   Verdict: enrich §16. The five-factor choice table (subtask count, window fit, parallelism, isolation, cost) and the 50% window rule sharpen the opening.

2. **Inter-agent communication mechanisms.** Three channels: tool-call arguments, shared filesystem, message bus. Framed as IPC's two paradigms, shared memory vs message passing.
   Book: 「维度一」通信机制小节, 「并行协调形态」消息总线.
   Coverage: §16 file inboxes are message passing, §12 board is shared state. The paradigm framing and the bus durability trade-off are absent.
   Verdict: enrich §16. Naming the two paradigms explains why the repo needs both inboxes and a board.

3. **Collaboration topology taxonomy.** Peer, manager (orchestration), decentralized (choreography), over isolated contexts.
   Book: 「维度二：协作拓扑」.
   Coverage: §16 builds a lead-plus-teammates team, §22 names orchestrator-workers as a graph shape. The taxonomy itself is absent.
   Verdict: enrich §16. One paragraph placing the lead-team design inside the three-topology space.

4. **New-information criterion.** Multi-agent beats one agent only when collaboration adds information the generator lacked: test results, screenshots, tool checks.
   Book: 「多 Agent 何时真正优于单 Agent」.
   Coverage: §21 says the verifier is the loop bottleneck. The general criterion and the equal-budget parity result are absent from §16.
   Verdict: enrich §16. It is the strongest published answer to "why spawn a team at all" and grounds the Why rows.

5. **Multi-stage role switching.** One trajectory, per-phase system prompt and tool set, phase gates as tool calls, review can route back to implementation.
   Book: 「多阶段角色转换」(实验 10-1).
   Coverage: §22 mounts agents as nodes but rebuilds `messages[]` per visit. A phase node that keeps one trajectory while swapping prompt and tools is absent.
   Verdict: enrich §22. Phase switching is a path graph with one backward edge; add it as a shared-trajectory node variant.

6. **Shared-context handoff (`transfer_to_agent`).** Any role hands control to another role; the full history rides along, so nothing is packed.
   Book: 「跨领域角色转换」(实验 10-2).
   Coverage: not covered. §16 handoffs are isolated messages.
   Verdict: enrich §16. A short contrast: shared-context handoff needs no packet but cannot parallelize.

7. **Agent virtual filesystem.** One mounted tree with four regions: private scratchpad, shared workspace, external mounts, read-only built-ins. Paths are the interface.
   Book: 「Agent 眼中的文件系统」(表10-4).
   Coverage: pieces exist (§7 skills as read-only files, §15 worktrees, §16 team memory dir). The four-region layout and its visibility and locking table are absent.
   Verdict: enrich §16. The region table is a compact answer to "where does team state live".

8. **OS process analogy.** Program is static prefix, process memory is trajectory, CPU is LLM, fork is spawn, kill is cancel. Actor model lineage.
   Book: 「不共享上下文的多 Agent 协作」(表10-3).
   Coverage: the repo teaches each primitive in its own section (§6, §13, §16, §17).
   Verdict: skip. A framing device, not a mechanism; the repo already maps the primitives one by one.

9. **Status query.** Pull-style status RPC is weak. Instead ask by message, read an agreed progress file, or tail the child's persisted trajectory. Stale mtime detects a stall.
   Book: 「Agent 间的通信与控制」状态查询.
   Coverage: §18 workers push an idle notice, §12 board holds task status. Progress files, trajectory tailing, and mtime stall detection are absent.
   Verdict: enrich §18. Stall detection gives the "stuck busy" failure bullet a concrete trigger.

10. **Recovery contract for side effects.** A persisted trajectory plus checkpoints rebuilds state, but external effects need idempotency keys and a status lookup before retry.
    Book: 「Agent 间的通信与控制」轨迹持久化.
    Coverage: §11 error recovery and §12/§22 resume own replay. Idempotency keys are a gap there.
    Verdict: skip. Belongs to §11/§12, outside this ticket's sections.

11. **Termination.** Graceful stop with cleanup and ack, forced kill as fallback. Cascade terminate on first success, with a lock so near-simultaneous winners settle once.
    Book: 「Agent 间的通信与控制」执行终止, 实验 10-6.
    Coverage: §17 owns the shutdown handshake, §16 cites Hermes lineage cascade cleanup. First-success cascade, the settle-once race, and the forced tier are absent.
    Verdict: enrich §17. Cascade-on-success is the missing second use of the shutdown protocol.

12. **Team resource scheduling.** Per-subtask step and token budgets, strong models only where needed, concurrency caps, preemption. Budget awareness beats raw step count.
    Book: 「资源与调度」, 「步骤预算与 Agent 性能」.
    Coverage: §21 owns single-loop budgets. Team-level allocation and concurrency caps are absent.
    Verdict: enrich §18. Budgets and caps attach naturally to board tasks and the worker pool.

13. **Proposer-reviewer and premature termination.** A reviewer with external feedback turns "done" from a claim into a proof. Three forms: fake done, early give-up, false success.
    Book: 「对等协作模式」.
    Coverage: §21 loop engineering owns the verifier loop, its budget, and escalation.
    Verdict: skip. Already the core of §21, outside this ticket's sections.

14. **Debate, brainstorm, panel.** Peer formats where agents discuss the same text.
    Book: 「扩展：其他对等协作模式」.
    Coverage: not covered.
    Verdict: skip. The book's own evidence says equal-budget debate matches a single agent; no mechanism worth adding.

15. **Manager pattern engineering.** Subagents registered as tools. Children return structured summaries, not trajectories.
    The planner is the bottleneck, so it gets the strongest model.
    Book: 「管理者模式：中心化协调」.
    Coverage: §6 owns summary returns, §16's lead is the manager. The planner-bottleneck result and the model placement advice are absent.
    Verdict: enrich §16. One Why-level line: spend the best model on the lead, citing Plan-and-Act.

16. **Handoff packet.** Task description with acceptance criteria, confirmed facts and constraints, artifact paths. Never the raw trajectory.
    Book: 「去中心化模式」移交包小节.
    Coverage: §16's failure list says "make messages self-contained" but never says what goes in one.
    Verdict: enrich §16. The three-part packet is the concrete fix for the vague-message failure mode.

17. **Decentralized frameworks.** MetaGPT: fixed SOP pipeline, message pool with role subscriptions.
    AutoGen group chat: shared transcript, central speaker selector, livelock risk. OpenAI Swarm: pure handoff network, loop cap.
    Book: 「去中心化模式：对等移交」.
    Coverage: not covered; §16 is lead-centric.
    Verdict: enrich §16. A short survey; subscription decoupling and handoff loop caps are reusable ideas.

18. **A2A protocol.** Cross-org interop: Agent Card discovery, a task lifecycle state machine (submitted, working, input-required, completed, failed), opaque artifact exchange.
    Book: 「跨组织协作：A2A 协议」.
    Coverage: §19 covers MCP (agent to tool). Agent-to-agent interop is absent; §17's states are per request, not per task.
    Verdict: enrich §17. Position A2A as the cross-trust-boundary layer above the in-team protocol and borrow its task-state vocabulary.

19. **MAST failure taxonomy and Byzantine framing.** 14 failure modes in three classes: system design, inter-agent misalignment, verification gaps.
    Agent failures are Byzantine, so only independent redundancy catches them.
    Book: 「多 Agent 协作的失败模式」.
    Coverage: §16/§17/§18 list per-mechanism failures; no taxonomy, no Byzantine framing.
    Verdict: enrich §16. One framing bullet plus the MAST citation upgrades the failure section.

20. **Shared-file concurrency.** Lost update vs semantic conflict. Optimistic locking checks a version on write; worktree isolation defers conflicts to one merge point.
    Book: 「失败模式一：共享文件系统的并发冲突」.
    Coverage: §16 locks inboxes, §12 locks claims, §15 owns worktrees. Optimistic locking and the semantic-conflict class are absent.
    Verdict: enrich §16. Two failure bullets: version-checked writes for shared files, and semantic conflicts need task-level separation.

21. **Error cascade amplification.** A wrong upstream fact gains credibility as agents repeat it.
    A checker that sees only conclusions calls the consistency correct. Break the chain with independent review over raw evidence.
    Book: 「失败模式二：错误的级联放大」.
    Coverage: not covered; §16's failures are transport-level, not semantic.
    Verdict: enrich §16. The strongest genuinely new failure mode in the chapter.

22. **Loop runaway triad.** Cost runaway, comprehension debt, cognitive surrender, and their fixes: budgets, grounded verifiers, a human who stays the loop engineer.
    Book: 「失败模式二」循环失控小节.
    Coverage: §21 owns loop budgets and escalation.
    Verdict: skip. §21 territory, outside this ticket's sections.

23. **Emergent agent society.** Stanford town (memory stream, reflection, planning, emergent parties),
    Agentopia (10-year simulation, life reward, fine-tuning on top trajectories), Moltbook (1.5M agents, emergent religion and protocols).
    Book: 「Agent 社会」.
    Coverage: not covered. The memory and reflection components overlap §9 and §5.
    Verdict: skip. Simulation research with no harness mechanism to reconstruct; revisit only if a systems-study track opens.

24. **Market-based coordination.** Vending-Bench Arena (competition, price wars, collusion), Pinchwork (agent-to-agent task market), RentAHuman (agents hire humans).
    Book: 「Agent 社会」经济涌现各小节.
    Coverage: not covered.
    Verdict: skip. Frontier products with no stable mechanism; A2A (entry 18) carries the interop part.

25. **Information asymmetry by a code judge.** A non-LLM referee holds global state and passes each agent only what its role may see.
    Book: 「信息不对称下的策略博弈：狼人杀」(实验 10-8).
    Coverage: not covered; §3 gates tools, not knowledge.
    Verdict: skip. A game-master pattern, niche for this repo's harness focus.

## Source-worthy citations

- Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (MAST), arXiv:2503.13657, 2025. For §16 failure framing.
- Tran, Kiela, *Single-Agent LLMs Outperform Multi-Agent Systems ... Under Equal Thinking Token Budgets*, arXiv:2604.02460, 2026. For the new-information criterion.
- Huang et al., *Large Language Models Cannot Self-Correct Reasoning Yet*, ICLR 2024. Also Kamoi et al., TACL 2024, arXiv:2406.01297. For §16/§21 Why rows.
- Erdogan et al., *Plan-and-Act*, arXiv:2503.09572, 2025. Planner is the bottleneck; strongest model to the lead.
- Anthropic, *How we built our multi-agent research system*, 2025. 15x token cost; token use explains most of the performance variance.
- Google A2A protocol spec (Linux Foundation). Agent Card, task states, opaque artifacts. For §17.
- MetaGPT (arXiv:2308.00352), AutoGen (arXiv:2308.08155), OpenAI Swarm / Agents SDK handoffs. For §16 topology survey.
- Moonshot AI, *Kimi Agent Swarm*, 2026. Scaled orchestrator-worker fan-out trained into the model. For §16 or §22 scale note.
- Park et al., *Generative Agents*, 2023. Only if an agent-society study ever opens.

## Contradictions

- Terminology. The book demotes "Graph Engineering" to a term note and keeps "collaboration topology" and "orchestration" as primary terms.
  The repo names §22 after the new term. Not factual conflict, but cross-references should not assume the book's vocabulary.
- Definition of multi-agent. The book counts shared-context role switching as multi-agent because prompt and tools change per phase.
  The repo would call that one agent with swapped prompts. State the definition when citing.
- Dispatch direction. The book's manager assigns tasks to children and never covers pull-based claiming.
  §18 argues lead assignment does not scale and workers claim from a board. Complementary, but the recommendations point opposite ways.
