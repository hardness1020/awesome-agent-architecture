# Book ch6 (Evaluation) vs section 20 (Observability & evaluation)

- Source: https://github.com/bojieli/ai-agent-book · `book/chapter6.md` (Chinese original, canonical).
- Date: 2026-08-05.
- Question: does ch6's evaluation material enrich section 20, or does evaluation deserve its own section?

## Answer

Evaluation deserves its own section. Section 20 keeps observability.

Section 20's mechanism is a side-observer pipeline (events, sinks, sampling, scrubbing, cost) plus a minimal offline `run_eval` that returns one pass rate.
The book treats evaluation as a full discipline: environments, datasets, judges, a metric dictionary, decision statistics, and eval-driven iteration.
Folding that into section 20 breaks the one-mechanism-per-section shape. A new section (candidate `23-evaluation`) should own it.
Section 20 keeps `run_eval` as its runnable hook and absorbs only the trace model, cost attribution, and the trace-to-eval-corpus loop.

## Mechanisms

### Model swap and ablation experiments
- What: fix the harness and swap models to locate the bottleneck; disable one harness component to measure its real contribution.
- Book heading: chapter opening (Agent 的评估).
- §20 coverage: none. `run_eval` grades a candidate build but never attributes a score change to model vs harness.
- Verdict: `candidate new section`. Attribution across the model-plus-harness combo is this repo's core thesis, and §20 has no room for it.

### Evaluation environment, five elements
- What: dataset, environment state, tool interface, rubric, and interaction protocol form a resettable automated test bed.
- Book heading: 自动评估环境 · 评估环境的基本组成.
- §20 coverage: `run_eval` has only tasks and graders. No state, no reset, no protocol.
- Verdict: `candidate new section`. The environment is the stage every other eval mechanism runs on.

### Tool-call environment hierarchy (Verifiers)
- What: layered env types (single turn, tool loop, stateful tools, sandbox) matched to task state and isolation needs, with trajectory caching.
- Book heading: 自动评估环境 · 工具调用型评估环境.
- §20 coverage: none.
- Verdict: `candidate new section`. Gives the new section a concrete per-system column (Verifiers).

### User simulation with progressive information disclosure
- What: an LLM plays the user and reveals information stepwise from a script; τ²-bench adds dual control (the simulated user also mutates shared state).
- Book heading: 自动评估环境 · 人机交互型评估环境.
- §20 coverage: none.
- Verdict: `candidate new section`. Interactive agents cannot be evaluated without it, and it is a mechanism, not a metric.

### Dataset design and contamination defense
- What: precision vs openness, difficulty tiers, parameterized templates, human-verified subsets, canary GUIDs, and fresh-issue collection against leakage.
- Book heading: 评估任务数据集的设计.
- §20 coverage: only the mitigation line "seed tasks from scrubbed traces" touches task distribution.
- Verdict: `candidate new section`. Dataset quality decides whether any pass rate means anything.

### Metric dictionary
- What: process metrics (action legality, path efficiency), Pass@k vs Pass^k vs Best@k, trajectory vs outcome checks, and zero-tolerance safety vetoes.
- Book heading: 评估指标体系.
- §20 coverage: one pass rate, effectively Pass@1 on a single run.
- Verdict: `candidate new section`. Regression gating needs Pass^k and process metrics, which do not fit §20's seven-line eval.

### LLM-as-a-Judge with rubric criteria
- What: rubric-driven judging with four criteria (expert-grounded, full coverage, weighted with veto items, self-contained), judge calibration on a gold set, red teaming.
- Book heading: 自动化评估方法 · LLM-as-a-Judge.
- §20 coverage: named only in Sources as reconstruction. No mechanism.
- Verdict: `candidate new section`. It is the scoring engine for every open-ended task the repo's agents produce.

### Multi-source heterogeneous judging
- What: judges from different model families to break shared blind spots (Goodhart's law); aggregate by agreement, escalate splits to humans.
- Book heading: 自动化评估方法 · 同源模型问题与多源评判.
- §20 coverage: none.
- Verdict: `candidate new section`. Rides with the judge mechanism; also carries the position-bias fix (judge twice with swapped order).

### Multimodal judging (TTS, ASR, UI, video)
- What: extend judging to audio and visual outputs; reference selection is itself eval design.
- Book heading: 自动化评估方法 · 多模态 LLM-as-a-Judge.
- §20 coverage: none.
- Verdict: `skip`. Media quality scoring sits outside the harness mechanisms this repo teaches.

### Pairwise comparison and Elo ranking
- What: Bradley-Terry based ranking from blind pairwise votes (Chatbot Arena style).
- Book heading: 配对比较与模型排名.
- §20 coverage: none.
- Verdict: `skip`. Leaderboard tooling, not a harness mechanism. The position-bias fix moves with the judge entry.

### Evaluation-driven model selection
- What: TTFT and decode throughput, thinking latency, rate limits, budget-capability curves, and default action-threshold behavior per model.
- Book heading: 评估驱动的模型选型.
- §20 coverage: none.
- Verdict: `skip`. A decision workflow over vendor metrics. The harness-relevant piece is the model swap experiment, covered above.

### Agent cost analysis
- What: context accumulation makes cost nonlinear, tool returns are re-billed every turn, cache and compression savings do not add, per-task cost caps.
- Book heading: 评估驱动的模型选型 · Agent 系统的成本分析.
- §20 coverage: per-model token totals priced into one session USD figure, plus a cost-drift failure mode.
- Verdict: `enrich §20`. §20 already owns cost; add why cost grows nonlinearly, per-task attribution, and per-task caps.

### Statistical significance
- What: binomial standard error as a noise band, repeated runs, paired per-task analysis (McNemar style), multiple-comparison correction.
- Book heading: 评估结果的统计显著性.
- §20 coverage: none. `run_eval` reports a raw single-run rate.
- Verdict: `candidate new section`. It guards every eval verdict. §20 needs only a one-line caveat that a small drop can be noise.

### Trace and span observability stack
- What: span trees per run (LLM call, tool call, retrieval as child spans), OpenTelemetry plus OpenInference conventions, async batched collection.
- Book heading: Agent 的可观测性.
- §20 coverage: flat fire-and-forget events with sinks. No span tree, no standard protocol.
- Verdict: `enrich §20`. Extends the existing telemetry mechanism directly; standards decouple collection from backends.

### Production traces feed the eval set
- What: filter failed and suspect production runs, scrub them, and land them as regression cases, so the eval set tracks the real distribution.
- Book heading: Agent 的可观测性 (回流成评估资产).
- §20 coverage: present as a one-line mitigation under the eval-production mismatch failure mode.
- Verdict: `enrich §20`. Promote the mitigation line into mechanism text; it is the interface between the two pipelines §20 already names.

### Benchmark report to improvement loop
- What: check the grader before blaming the agent, localize failure clusters, change one variable per round, scale evidence before deploying.
- Book heading: 从 Benchmark 报告到系统改进.
- §20 coverage: none.
- Verdict: `candidate new section`. Eval-driven harness iteration is the payoff of an evaluation section.

### Internal evaluation infrastructure
- What: ablation master switches, AB tests separating mechanism from goal metrics with guardrails, dual-layer feature flags, prompt snapshot regression, typed privacy analytics.
- Book heading: 从外部评估到内部评估.
- §20 coverage: the scrub allowlist parallels typed privacy analytics; ablation, AB, flags, and prompt regression are absent.
- Verdict: `candidate new section`. Evaluation embedded in the production harness; only the privacy piece is already §20's.

### Simulation environments for post-training
- What: eval environments upgraded for millions of episodes (reset semantics, throughput, randomization); verifiers become RLVR reward functions.
- Book heading: 仿真环境：从评估到后训练的桥梁.
- §20 coverage: none.
- Verdict: `skip`. Post-training territory, outside the harness loop this repo teaches.

## Source-worthy citations

- Verifiers framework, environment hierarchy and trajectory caching: https://github.com/willccbb/verifiers
- τ-bench and τ²-bench (Sierra), user simulation, dual control, binary reward, Pass^k:
  https://github.com/sierra-research/tau-bench · https://github.com/sierra-research/tau2-bench
- SWE-bench Verified (OpenAI), 500-task human-verified subset, FAIL_TO_PASS and PASS_TO_PASS checks.
- GAIA benchmark, three difficulty levels, answer uniqueness as contamination defense.
- AndroidWorld, parameterized task templates, final-UI-state verification: https://github.com/google-research/android_world
- OSWorld and OSWorld-Verified, 134 deep-check evaluation functions, 300+ issues fixed, 50x parallel on AWS.
- Terminal-Bench, canary GUID leak detection, executable verification: https://github.com/laude-institute/terminal-bench
- Scale AI, "Rubrics as Rewards", the rubric four criteria and veto weighting.
- RE-Bench, budget-capability curves for humans vs agents: arXiv:2411.15114 (as cited by the book).
- OpenTelemetry plus OpenInference semantic conventions for LLM spans.
- ClawBench, real-site end-to-end tasks with five evidence layers (as cited by the book): https://github.com/TIGER-AI-Lab/ClawBench

## Contradictions and tensions

- §20 frames evaluation as strictly offline and off the hot path. The book's internal-eval section runs AB tests, ablation switches, and prompt regression inside production.
  The §20 framing is incomplete rather than wrong; a new section resolves it.
- §20 calls a lower `run_eval` rate "the release signal". The book shows a 3-point gap on 100 cases sits inside the noise band, and single runs drift. The claim needs a caveat.
- §20 rolls spend into one session USD total. The book argues per-task cost varies by orders of magnitude, so a single total hides runaway tasks; it wants per-task caps.
- Naming: §20 uses "evaluation" for a fixed-task pass rate. The book's evaluation includes the environment, the judge, and decision statistics.
  The shared word hides the scope gap, which is itself the argument for splitting.
