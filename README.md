# Awesome Agent Architecture

[![Focus: Harness Engineering](https://img.shields.io/badge/focus-harness%20engineering-6e40c9)](#the-premise)
[![Systems: 1+](https://img.shields.io/badge/systems-1%2B-0a7bbb)](#systems-under-study)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> How modern AI agents are actually built. A side by side teardown of the harness around the model.

Every capable agent shares one anatomy: a small loop, wrapped in a harness of tools, memory, permissions, and interfaces. This repo takes that harness apart and compares how real systems build each piece.

**Contents:** [Premise](#the-premise) · [Systems](#systems-under-study) · [The Loop](#the-agent-loop) · [Sections](#sections) · [Method](#method) · [Structure](#repository-structure) · [Running](#running-the-demos)

---

## The Premise

The capability comes from the **model**. The engineering is the **harness** around it: the loop, tools, memory, permissions, and interfaces that let the model act.

> The model is the engine. The harness is the chassis, steering, and dashboard.

Learn the harness once and you can read any agent. A coding tool, a chat assistant, and an autonomous runner are the same machine with different harness choices. **Claude Code**, for example, is a disciplined coding tool with tight tools, permissions, subagents, and skills.

---

## Systems Under Study

Each system is a worked example for every section below.

| System                | Maintainer | License     | Models      | Surface       | Read it for                    |
| --------------------- | ---------- | ----------- | ----------- | ------------- | ------------------------------ |
| **Claude Code** | Anthropic  | Proprietary | Claude only | CLI, IDE, web | Permissions, subagents, skills |
| *(more soon)*       |            |             |             |               |                                |

> More open source agents will be added (Hermes Agent, OpenClaw, aider, mini-swe-agent, and others). Each fills the same columns.

---

## The Agent Loop

Strip the branding and nearly every agent is the same loop. Everything else is a section hanging off it.

```mermaid
flowchart LR
    U([User intent]) --> M["messages[]"]
    M --> L{{LLM}}
    L -->|stop_reason: tool_use| T[Tool runtime]
    T --> P{Permitted?}
    P -->|deny / ask| M
    P -->|allow| X[Execute tool]
    X --> R[Tool result] --> M
    L -->|stop_reason: end_turn| D([Reply to user])
```

The loop is trivial. The real work is what wraps it: dispatching and gating tools, keeping context from overflowing, persisting state across turns, and making many loops cooperate.

---

## Sections

Seven layers, from a bare loop to a self coordinating system. Each row is one self contained writeup.

| #  | Section                                                    | Key question                             | Key mechanisms                                                                            |
| -- | ---------------------------------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------------------------- |
|    | **Layer 0 · Foundations**                           |                                          |                                                                                           |
| 0  | [Harness thesis](sections/00-harness-thesis/)                 | Where does agency come from?             | model vs orchestration; harness = tools + knowledge + observation + actions + permissions |
|    | **Layer 1 · Core Loop**                             |                                          |                                                                                           |
| 1  | [Agent loop](sections/01-agent-loop/)                         | How does an agent keep going?            | `messages[]`, `while True`, `stop_reason`                                           |
| 2  | [Tool runtime](sections/02-tool-runtime/)                     | How are tools called and routed?         | dispatch map, schemas, parallel calls, deferred search                                    |
| 3  | [Permission &amp; sandbox](sections/03-permission-sandbox/)   | How are side effects gated?              | approval pipeline, permission modes, sandboxing                                           |
| 4  | [Hooks](sections/04-hooks/)                                   | How to extend without forking the loop?  | `PreToolUse`, `PostToolUse`, interception points                                      |
|    | **Layer 2 · Complex Work**                          |                                          |                                                                                           |
| 5  | [Planning &amp; todos](sections/05-planning-todos/)           | How is big work decomposed?              | plan mode, todo list, plan then execute                                                   |
| 6  | [Subagents](sections/06-subagents/)                           | How is a sub problem isolated?           | fresh`messages[]`, delegation, context isolation                                        |
| 7  | [Skills](sections/07-skills/)                                 | How are capabilities added on demand?    | manifests, on demand injection, autogeneration                                            |
| 8  | [Context management](sections/08-context-management/)         | How do long sessions fit the window?     | micro / snip / auto compaction, token budgets                                             |
|    | **Layer 3 · Knowledge & Resilience**                |                                          |                                                                                           |
| 9  | [Memory](sections/09-memory/)                                 | How does it remember across runs?        | selection, extraction, consolidation, recall                                              |
| 10 | [System prompt assembly](sections/10-system-prompt/)          | How is the prompt built each turn?       | runtime composition, section concatenation                                                |
| 11 | [Error recovery](sections/11-error-recovery/)                 | How does a long task survive failure?    | retries, token escalation, model fallback                                                 |
|    | **Layer 4 · Long Running & Async**                  |                                          |                                                                                           |
| 12 | [Task system](sections/12-task-system/)                       | How does work persist beyond a turn?     | task records,`blockedBy` deps, disk persistence                                         |
| 13 | [Background execution](sections/13-background-execution/)     | How does work run off the main loop?     | threaded execution, notification queue                                                    |
| 14 | [Scheduling](sections/14-scheduling/)                         | How does an agent act on a clock?        | cron, wakeups, durable triggers                                                           |
| 15 | [Worktree isolation](sections/15-worktree-isolation/)         | How does parallel work avoid collisions? | worktree records, task directory binding                                                  |
|    | **Layer 5 · Multi Agent**                           |                                          |                                                                                           |
| 16 | [Coordination](sections/16-coordination/)                     | How do many agents talk?                 | message bus, inbox, permission bubbling                                                   |
| 17 | [Protocols](sections/17-protocols/)                           | How do agents agree and stop cleanly?    | plan approval, shutdown handshake                                                         |
| 18 | [Autonomy](sections/18-autonomy/)                             | How do agents organize themselves?       | idle cycle, auto claim, self organization                                                 |
|    | **Layer 6 · Extension & Integration**               |                                          |                                                                                           |
| 19 | [MCP / plugins / channels](sections/19-mcp-plugins-channels/) | How does the harness reach the world?    | multi transport, channel routing, tool pool assembly                                      |
| 20 | [Observability &amp; evaluation](sections/20-observability/)  | How do we know it works?                 | tracing, metrics, eval harnesses, failure modes                                           |

---

## Method

Every section is read the same way:

1. **Problem.** What fails if you leave it out.
2. **Mechanism.** The data structures and control flow, named concretely.
3. **Per system.** How each agent implements it, and the trade-offs.
4. **Failure modes.** What breaks in production.

Analyses favor named, verifiable mechanisms over hand waving, each paired with a diagram or minimal pseudo code.

---

## Repository Structure

> All 21 section writeups are built, `00-harness-thesis/` through `20-observability/` (linked from the Sections table above). The other folders are the roadmap.

```text
awesome-agent-architecture/
├── README.md                  # the map
├── sections/                # one folder per section (rows of the Sections table)
│   ├── 00-harness-thesis/     # README.md per section
│   ├── 01-agent-loop/src/     # sections 1 to 14 carry a runnable src/ that grows:
│   └── 20-observability/      #   each section adds one file and evolves loop.py
├── systems/                   # per system deep dives (claude-code/, ...)
├── patterns/                  # cross cutting patterns and failure modes
└── references/                # primary sources and prior art
```

Each section folder is `NN-name/`, numbered to match its Sections row, holding a `README.md`. Sections 1 to 14 also carry a `src/` whose code accumulates section by section: each adds one file and evolves `loop.py`, so `diff` between two sections shows exactly what that section added. New systems and sections slot into the same folders.

---

## Running the demos

Sections 1 to 14 ship a runnable `src/`. One-time setup with [uv](https://docs.astral.sh/uv/), from the repo root:

```bash
uv venv
uv pip install -r requirements.txt
cp .env.example .env        # then add your ANTHROPIC_API_KEY
```

Pinned deps are in [`requirements.txt`](requirements.txt) (`anthropic==0.112.0`, `python-dotenv==1.2.2`). `.env` (gitignored) holds `ANTHROPIC_API_KEY`, plus optional `ANTHROPIC_MODEL` (defaults to `claude-sonnet-4-6`) and `ANTHROPIC_BASE_URL`. The demos load it automatically. Each section has a `demo.py` (live, against the API) and a `test.py` (offline checks, no key needed):

```bash
python sections/01-agent-loop/src/test.py         # offline, no key
uv run python sections/01-agent-loop/src/demo.py  # live
```

---

## Contributing

- **Add a system.** Slot a new agent into the existing sections.
- **Deepen a section.** Add a mechanism, a clearer diagram, or a sharper failure analysis.
- **Correct the record.** These are reconstructions from public docs and behavior. Sourced corrections are welcome.

Open an issue or PR. Favor named, verifiable mechanisms over speculation, and cite sources.

---

## References

| Source                                                             | What it offers                                                                                                                    |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| [claude-code](https://github.com/yasasbanukaofficial/claude-code)     | Backup of Claude Code's leaked TypeScript source, the grounding for mechanism names (`QueryEngine.ts`, `query/`, `Tool.ts`) |
| [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | 20 lesson code first harness reconstruction, the depth benchmark                                                                  |

---

## License

[MIT](LICENSE). Analyses are educational reconstructions from public documentation and observed behavior, not official descriptions of any system.
