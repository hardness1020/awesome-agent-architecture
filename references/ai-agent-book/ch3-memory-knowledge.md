# Book ch3 · Memory and Knowledge Bases vs section 9

- Source: [ai-agent-book](https://github.com/bojieli/ai-agent-book), `book/chapter3.md` (用户记忆和知识库), Chinese original, canonical.
- Date: 2026-08-05.
- Question: which ch3 mechanisms does this repo or learn-agent-memory already cover,
  and is RAG / knowledge-base retrieval a real gap in this repo's harness story?

Boundary rule: this repo keeps the section 9 teaching core.
Deep memory work belongs to [learn-agent-memory](https://github.com/hardness1020/learn-agent-memory) (LAM below, LAM §N means its section N).

## Per mechanism

Each item: name, one-line description, book heading, current coverage, verdict.

1. **Run-end fact extraction.** A dedicated LLM call distills selective, abstracted, structured facts after a conversation.
   Heading: 用户记忆系统. Coverage: §9 Extraction operation, LAM §3 write policy.
   Verdict: skip. This is already the core of §9.

2. **Three-level memory evaluation.** Basic recall, multi-session retrieval, proactive service, benchmarked LoCoMo style.
   Heading: 记忆能力的评估：三层次框架. Coverage: LAM §10 evaluation and governance.
   Verdict: defer to learn-agent-memory. Evaluation is a memory-subsystem concern, not harness teaching core.

3. **Memory tiers.** Append-only trajectory for the run, long-term store across runs, optional business state.
   Heading: 记忆的层次结构. Coverage: §9 (`messages[]` vs store, raw session log), LAM §2 event ledger.
   Verdict: skip. §9 already separates the run record from the durable store.

4. **Four storage formats.** Simple Notes to Advanced JSON Cards, granularity vs disambiguation trade-off.
   Heading: 用户记忆的四种存储格式. Coverage: LAM §4 typed records, LAM §7 profile view.
   Verdict: defer to learn-agent-memory. Record schema design is deep memory work.

5. **Executable-code memory.** User state as typed Python, fact log plus periodic regeneration, checks run as code (User as Code).
   Heading: 进阶知识表示形态：可执行代码. Coverage: none.
   Verdict: defer to learn-agent-memory. A representation choice for its typed-memory and consolidation stages.

6. **Cognitive memory types.** Episodic, semantic, procedural split, plus working memory as the context window.
   Heading: 用户记忆的认知科学基础. Coverage: LAM §4 uses the same taxonomy.
   Verdict: skip. Already taught where it belongs.

7. **Memory framework studies.** Mem0 (write-time gate in v2, append-only plus hybrid retrieval in v3), Memobase (profile slots plus event timeline).
   Heading: 记忆框架案例. Coverage: LAM §3 covers Mem0's write gate; Memobase uncovered.
   Verdict: defer to learn-agent-memory. System studies for its write-policy and temporal sections; see contradictions on Mem0 v3.

8. **Compression and consolidation.** Importance scoring, clustering to summaries, abstraction to rules, versioned conflicts.
   Heading: 记忆压缩与整理机制. Coverage: §9 Consolidation operation, LAM §5 and §6 in depth.
   Verdict: skip. §9 names the operation; depth already lives in LAM.

9. **PII log sanitization.** A local small model detects and redacts sensitive data before logs or context see it.
   Heading: 隐私保护：日志脱敏. Coverage: LAM §1 sensitivity, thinner than the book.
   Verdict: defer to learn-agent-memory. Privacy of stored memory is a contract concern there.

10. **RAG pipeline basics.** Chunking, dense embeddings with ANN, BM25 sparse retrieval, hybrid fusion (RRF), neural reranking, recall@k metrics.
    Heading: RAG 基础：构建 Agent 的知识获取管道. Coverage: LAM §7 index views, §8 hybrid retrieval, §10 metrics; §9 teaches BM25 log search at toy scale.
    Verdict: defer to learn-agent-memory. Retrieval internals sit below the harness; LAM already owns sparse, dense, hybrid.

11. **Structured indexes.** RAPTOR tree summaries and GraphRAG entity-relation graphs for cross-document and multi-hop queries.
    Heading: 结构化索引：从信息检索到知识建模. Coverage: LAM §7 graph and wiki views, Graphiti/Zep study.
    Verdict: defer to learn-agent-memory. Index structure is a memory-view decision there. Note: repo section 22 is workflow graphs, unrelated.

12. **File-system knowledge paradigm.** Knowledge as files with URIs, L0/L1/L2 layered summaries, wiki-style cross-links (OpenViking).
    Heading: 文件系统范式：用目录结构组织知识. Coverage: §9 frontmatter index and manifest, §7 progressive disclosure are the same shape.
    Verdict: enrich §9. Add the failure mode the book isolates (files without cross-links degrade into unsearchable islands) plus one source line.

13. **Knowledge update as PRs.** Proposer agent commits a diff, cross-family reviewer agent audits against raw evidence, indexes rebuilt after merge.
    Heading: 知识应该如何更新 (增量更新). Coverage: LAM §6 propose-validate-commit, thinner than the book.
    Verdict: defer to learn-agent-memory. Governance of the store belongs to its consolidation stage.

14. **Periodic full consolidation.** Scheduled dedupe, re-check against raw evidence, conflict qualification, staleness metadata, tenant-scoped retrieval filters.
    Heading: 知识应该如何更新 (定期整理). Coverage: LAM §1 tenancy, §5 supersede, §6 cold path.
    Verdict: defer to learn-agent-memory. Same governance track as item 13.

15. **Agentic RAG.** Retrieval wrapped as a tool the model calls in a think-act-observe loop, multi-round query refinement.
    Heading: 智能体化 RAG：将知识检索工具化的范式转变. Coverage: §9 `SessionSearch` tool vs harness recall, "who pulls the trigger".
    Verdict: skip. §9 already teaches both trigger paths; the rest is retrieval depth (item 10).

16. **RAG security boundary.** Retrieved documents carry indirect prompt injection; tag sources as data, gate side effects separately.
    Heading: RAG 的安全边界 (inside 智能体化 RAG). Coverage: §3 permission gating, LAM §9 untrusted-data framing.
    Verdict: skip. Split correctly across §3 and LAM already.

17. **Contextual retrieval.** An LLM writes a context prefix per chunk before indexing, boosting both BM25 and embeddings (Anthropic).
    Heading: RAG 技巧：上下文感知检索. Coverage: LAM §8 (MemMachine contextual retrieval).
    Verdict: defer to learn-agent-memory. An index-time retrieval technique, squarely LAM §8 material.

18. **Dual-layer memory architecture.** Small structured cards resident in context for overview, contextual retrieval on demand for detail.
    Heading: 实验 3-12 and 本章小结. Coverage: §9's two stores (injected distilled facts plus searchable raw log) are this shape at teaching scale.
    Verdict: skip. The shape is taught; the production version is LAM's pipeline.

19. **Knowledge discovery from datasets.** LLM turns case records into schemas, clustering finds prototypes and factor weights.
    Heading: 从数据集中提取深度知识. Coverage: none.
    Verdict: skip. Data engineering on corpora, not a harness mechanism.

20. **Multimodal memory.** Store raw media plus text index, or embeddings in context, or parametric slot edits (User as Engram).
    Heading: 前沿探索：多模态记忆. Coverage: none.
    Verdict: skip. Research frontier with no settled harness mechanism to teach yet.

## Is RAG / knowledge-base retrieval a gap here?

No new section. The harness needs two integration points and section 9 has both:
harness-side recall injected before the turn, and retrieval as a read-only tool the model calls mid-turn.
Everything below that line (chunking, embeddings, BM25 math, fusion, reranking, RAPTOR, GraphRAG) is a data subsystem,
and the boundary rule sends it to learn-agent-memory, whose index-views and hybrid-retrieval sections already own it.
The one shared-knowledge-base idea the book adds that LAM does not yet stress is tenant-scoped retrieval filtering, a LAM contract concern.
Net result: one small enrich for §9 (item 12), the rest defers or is covered.

## Source-worthy citations

- Anthropic, Contextual Retrieval. https://www.anthropic.com/engineering/contextual-retrieval
- Mem0: Chhikara et al., arXiv:2504.19413, plus the OSS v2 to v3 migration guide. https://docs.mem0.ai/migration/oss-v2-to-v3
- LoCoMo: Maharana et al., arXiv:2402.17753.
- RAPTOR: Sarthi et al., arXiv:2401.18059. GraphRAG: Edge et al., arXiv:2404.16130.
- OpenViking. https://github.com/volcengine/OpenViking
- Memobase. https://github.com/memodb-io/memobase
- User as Code (arXiv:2606.16707) and User as Engram (arXiv:2606.19172), both Li 2026, the book author's own preprints.

## Contradictions

- Mem0 framing. LAM §3 teaches Mem0 as the write-time LLM gate (ADD, UPDATE, DELETE, NOOP).
  The book reports v3 (2026-04) dropped write-time resolution for append-only ADD plus hybrid retrieval, and calls the Mem0-g graph variant historical.
  LAM's Mem0 study may describe a superseded design; worth an update ticket there.
- Metrics naming. The book's "recall@k" is hit rate (success@k) and says so itself; its 49% and 67% failure-rate numbers use that meaning. Compare across sources with care.
- Framing, not fact. The book makes RAG a core agent capability; this repo's thesis keeps retrieval internals below the harness. Both hold given each project's scope.
- Single-source claims. The two headline representation designs (User as Code, User as Engram) are the author's own preprints; no independent replication cited.
