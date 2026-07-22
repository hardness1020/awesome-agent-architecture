# 20 · Observability & evaluation

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> You cannot fix what you cannot see, and you cannot trust what you never measured.

An agent runs unattended, takes side effects, and spends money. A model call is a black box: it burns tokens and triggers real actions.

Without instrumentation you cannot answer the basic questions. What did it do. How often did a tool fail. What did this session cost. Did the last release get worse.

Two jobs answer them. Observability watches production: one event per step, tracked spend, reconstructable runs. Evaluation decides if a change made quality better or worse.

Leave both out and every regression ships silently, every cost spike is a surprise, and every bug report is unreproducible because nothing was recorded.

---

## Mechanism

![Mechanism diagram](assets/20-observability.png)

Two separable pipelines that never touch the loop's control flow.

Telemetry runs inline: each step calls a fire-and-forget logger.

Events go to sinks, destinations such as the terminal, a file, or a backend like Datadog. The logger queues events until a sink attaches, then samples, scrubs sensitive fields, and fans out.

Evaluation runs offline: replay a fixed task set against a candidate build and grade each output.

- `emit` never blocks and never raises, so a logging fault cannot stall or crash the loop (section 1).
- Events buffer in a queue until a sink attaches, then drain, so the loop can log before telemetry is ready.
- Sampling drops events by rate; scrubbing keeps only allowlisted fields, so code and paths never leak.
- Cost accumulates per model into one USD total, surfaced live and on exit.
- Eval is off the hot path: it grades a fixed task set, so a quiet quality drop is caught before users hit it.

### New: fire-and-forget event logging

`telemetry.py` emits events that queue until a sink attaches, then sample, scrub, and fan out. `emit` never raises:

```python
def emit(self, name, **meta):                          # src/telemetry.py
    if not self.sinks:
        self._queue.append((name, meta))               # buffer until a sink is ready
        return
    self._deliver(name, meta)

def _deliver(self, name, meta):
    if not self.sample(name):                          # dropped by sampling rate
        return
    clean = scrub(meta)                                # allowlist before any backend sees it
    for sink in self.sinks:
        try:
            sink(name, clean)
        except Exception:                              # one bad sink never breaks the loop
            pass
```

- Before any sink attaches, events buffer in `_queue`; `attach` drains them through the same `_deliver` path, so queued events are sampled and scrubbed too.
- `scrub` keeps only `SAFE_FIELDS`, so a value not known safe (code, a file path, a prompt) never reaches a backend.
- A sink that throws is swallowed, so one broken backend cannot stall or crash the loop.

### New: per-model cost and offline eval

Cost accumulates per model into one running USD total:

```python
def add(self, model, input_tokens, output_tokens):    # src/telemetry.py
    i, o = self.by_model.get(model, (0, 0))
    self.by_model[model] = (i + input_tokens, o + output_tokens)
    pi, po = PRICES.get(model, (0.0, 0.0))             # modelCost.ts pricing tiers
    self.cost_usd += input_tokens * pi + output_tokens * po
    return self.cost_usd
```

And evaluation replays a fixed task set against a candidate build and grades each output:

```python
def run_eval(build, tasks):                            # src/telemetry.py
    verdicts = [bool(grade(build(inp))) for inp, grade in tasks]
    passed = sum(verdicts)
    return {"passed": passed, "total": len(tasks), "rate": passed / len(tasks), "verdicts": verdicts}
```

- `add` looks up per-token pricing and rolls the spend into `cost_usd`, the number surfaced live and on exit.
- `run_eval` grades each output with its rubric and returns a pass rate; a regressed build scores lower, the release signal.
- The two pipelines share a vocabulary (event names, cost units), so a metric that drifts maps back to an eval that should have caught it.

### How it integrates

The demo rides telemetry on the model wrapper. The loop does not change:

```python
def model(messages, registry, system):
    r = client.messages.create(...)
    cost.add(MODEL, r.usage.input_tokens, r.usage.output_tokens)   # cost rollup
    tel.emit("model_call", model=MODEL, tokens=..., cost_usd=...)  # scrubbed event
    return r
run_turn([...goal...], lambda m, r, s: model(m, r, SYSTEM), reg, Session(mode=DEFAULT))   # the one agent call
```

- Telemetry observes from outside: the wrapper emits an event and tracks cost, so `run_turn` and dispatch stay byte-identical to section 13.
- The sink prints each event; the session cost prints at the end; then an offline `run_eval` grades a fixed task set.
- Everything upstream is unchanged. Observability is a side-observer, not a new step in the loop.

---

## Per system

How each agent emits telemetry, tracks spend, and measures quality.

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | Rich production visibility, cheap and safe. A bad sink never stalls the loop. | Even a crashed run leaves a file. Files double as audit log and eval corpus. |
| **Cons** | Only says what happened, not if the answer was good. No eval ships to catch a quiet regression. | Almost no production telemetry. No live event stream to watch. |
| **Why** | Production must be watched for crashes and cost spikes, without touching the loop. | Quality is graded offline by benchmark, so the full run record matters most. |
| **How: telemetry** | Events queue until a sink attaches, then sample, scrub, and fan out. | One trajectory file per run: messages, config, cost, exit status, saved each step. |
| **How: cost tracking** | Per-model tokens priced into one session USD total, shown on exit. | litellm prices each call into run and global totals; unknown models raise errors. |
| **How: evaluation** | Not in source; reconstruction: held-out tasks scored per build. | A SWE-bench batch runner ships in the repo, one container per task; batches resume. |

---

## Failure modes

- **Telemetry on the hot path.** A logging call that blocks or throws stalls the loop (section 1). Mitigation: fire-and-forget with a pre-sink queue and per-sink killswitch.
- **Sensitive data leaks into logs.** Code, file paths, or prompts land in a general-access backend. Mitigation: allowlist loggable fields and scrub the rest before fan-out.
- **Cost drift goes unnoticed.** A model swap or runaway loop multiplies spend. Mitigation: per-model totals surfaced live and on exit, plus the loop's step ceiling (section 1).
- **No regression signal.** Without an eval suite, a prompt or harness change ships and quality drops silently. Mitigation: a held-out task set scored per build, gating releases.
- **Eval-production mismatch.** Offline tasks miss real usage, so the suite passes while users fail. Mitigation: seed tasks from scrubbed traces so both share a distribution.

---

## Runnable

[`src/`](src/) carries 19 forward and adds:

- [`telemetry.py`](src/telemetry.py): the event logger (`Telemetry.emit`, queue and drain, `sample`, `scrub`), the per-model `CostTracker`, and the offline `run_eval`.
- [`test.py`](src/test.py): queue-then-drain, sampling, scrub plus sink isolation over a real tool dispatch, per-model cost, and an eval that catches a regressed build.
- [`demo.py`](src/demo.py): one agent turn observed by telemetry on the model wrapper, a live session cost, then an offline eval.

The loop and dispatch do not change. Telemetry observes from outside; eval runs off the hot path.

```bash
python sections/20-observability/src/test.py         # offline checks, no key
uv run python sections/20-observability/src/demo.py  # live demo, needs a key
```

---

## Sources

- [Claude Code analytics](https://github.com/yasasbanukaofficial/claude-code):
  `services/analytics/index.ts` (queue + `logEvent`), `sink.ts`, `datadog.ts`, `firstPartyEventLogger.ts`, `sinkKillswitch.ts`, `shouldSampleEvent`.
- [Claude Code cost and diagnostics](https://github.com/yasasbanukaofficial/claude-code):
  `cost-tracker.ts`, `utils/modelCost.ts`, `costHook.ts` (`formatTotalCost`), `diagnosticTracking.ts`, `upstreamproxy/relay.ts`.
- Evaluation is not present in this source. Eval harnesses, SWE-bench-style suites, and LLM-as-judge are described as reconstruction and general practice.
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent):
  `serialize` and `save` in `agents/default.py`, `GLOBAL_MODEL_STATS` in `models/__init__.py`, `run/benchmarks/swebench.py`, `run/utilities/inspector.py`.
- Framing: [learn-claude-code · s20_comprehensive](https://github.com/shareAI-lab/learn-claude-code).
