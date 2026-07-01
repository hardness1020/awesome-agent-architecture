# Awesome Agent Architecture

[![Focus: Harness Engineering](https://img.shields.io/badge/focus-harness%20engineering-6e40c9)](#sections)
[![Systems: 1+](https://img.shields.io/badge/systems-1%2B-0a7bbb)](#systems-under-study)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> How modern AI agents are built around the model.

The model provides reasoning. The harness provides action, state, and limits.

A model call can produce text or request a tool.
It cannot run the tool, remember state across calls, gate side effects, or coordinate other loops by itself.
The harness does that work.

This repo explains the harness section by section: loop, tools, memory, permissions, context, tasks, and interfaces.
Each section teaches one mechanism and compares it with real systems.

Learn the harness once and you can read many agents. A coding tool, chat assistant, and autonomous runner mostly differ in harness choices.

**Contents:** [Systems](#systems-under-study) · [Loop](#the-agent-loop) · [Sections](#sections) ·
[Method](#method) · [Structure](#repository-structure) · [Running](#running-the-demos)

---

## Systems Under Study

Each system is a worked example for the sections below.

| System | Maintainer | License | Models | Surface | Read it for |
| --- | --- | --- | --- | --- | --- |
| **Claude Code** | Anthropic | Proprietary | Claude only | CLI, IDE, web | Permissions, subagents, skills |
| *(more soon)* | | | | | |

> More systems can be added later, including Hermes Agent, OpenClaw, aider, and mini-swe-agent.

---

## The Agent Loop

Most agents share the same control flow: call the model, run requested tools, append results, and call the model again.

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

The loop is small. Most engineering is around it: dispatch tools, gate side effects, manage context, persist state, and coordinate other loops.

---

## Sections

Seven layers, from the basic loop to a multi-agent harness. Each row links to one self-contained writeup.

| # | Section | Question | Key mechanisms |
| --- | --- | --- | --- |
| | **Layer 0 · Foundations** | | |
| 0 | [Harness thesis](sections/00-harness-thesis/) | Where does agency come from? | Model vs harness, actions, observations, permissions |
| | **Layer 1 · Core Loop** | | |
| 1 | [Agent loop](sections/01-agent-loop/) | How does an agent keep going? | `messages[]`, loop, `stop_reason` |
| 2 | [Tool runtime](sections/02-tool-runtime/) | How are tools called and routed? | Registry, schemas, dispatch, deferred search |
| 3 | [Permission & sandbox](sections/03-permission-sandbox/) | How are side effects gated? | Permission modes, approvals, sandboxing |
| 4 | [Hooks](sections/04-hooks/) | How do extensions attach to the loop? | `PreToolUse`, `PostToolUse`, lifecycle events |
| | **Layer 2 · Complex Work** | | |
| 5 | [Planning & todos](sections/05-planning-todos/) | How is big work decomposed? | Plan mode, todo list, approval before edits |
| 6 | [Subagents](sections/06-subagents/) | How is a subproblem isolated? | Fresh `messages[]`, delegation, child loop |
| 7 | [Skills](sections/07-skills/) | How are capabilities loaded on demand? | `SKILL.md`, catalog, progressive disclosure |
| 8 | [Context management](sections/08-context-management/) | How do long sessions fit the window? | Budgeting, stubs, compaction, summaries |
| | **Layer 3 · Knowledge & Resilience** | | |
| 9 | [Memory](sections/09-memory/) | How does it remember across runs? | Selection, recall, extraction, consolidation |
| 10 | [System prompt assembly](sections/10-system-prompt/) | How is the prompt built each turn? | Prompt sections, live state, cache boundaries |
| 11 | [Error recovery](sections/11-error-recovery/) | How does a long task survive failure? | Retries, overflow recovery, fallback model |
| | **Layer 4 · Long Running & Async** | | |
| 12 | [Task system](sections/12-task-system/) | How does work persist beyond a turn? | Task records, dependencies, locks |
| 13 | [Background execution](sections/13-background-execution/) | How does work run off the main loop? | Handles, task state, notification queue |
| 14 | [Scheduling](sections/14-scheduling/) | How does an agent run later? | Cron, sleep, remote triggers, queues |
| 15 | [Worktree isolation](sections/15-worktree-isolation/) | How does parallel work avoid collisions? | Git worktrees, cwd binding, safe cleanup |
| | **Layer 5 · Multi Agent** | | |
| 16 | [Coordination](sections/16-coordination/) | How do many agents talk? | Inboxes, broadcasts, permission bubbling |
| 17 | [Protocols](sections/17-protocols/) | How do agents agree and stop cleanly? | Plan approval, shutdown handshakes |
| 18 | [Autonomy](sections/18-autonomy/) | How do agents organize themselves? | Idle cycle, task claiming, self organization |
| | **Layer 6 · Extension & Integration** | | |
| 19 | [MCP / plugins / channels](sections/19-mcp-plugins-channels/) | How does the harness reach the world? | Transports, channels, tool pool assembly |
| 20 | [Observability & evaluation](sections/20-observability/) | How do we know it works? | Tracing, metrics, evals, failure analysis |

---

## Method

Every section uses the same lens:

1. **Opening.** What problem this layer solves.
2. **Mechanism.** The general design and control flow.
3. **Per system.** How real systems implement it.
4. **Failure modes.** What breaks and how to mitigate it.

Mechanisms should be named and verifiable. Diagrams and small code snippets are preferred over vague description.

---

## Repository Structure

All 21 section writeups are present, from `00-harness-thesis/` through `20-observability/`.

```text
awesome-agent-architecture/
├── README.md                  # top-level map
├── sections/                  # one folder per section
│   ├── 00-harness-thesis/     # README.md per section
│   ├── 01-agent-loop/src/     # runnable chain starts here
│   └── 20-observability/
├── systems/                   # per-system deep dives
├── patterns/                  # shared patterns and failure modes
└── references/                # primary sources and prior art
```

Each section folder is `NN-name/` and contains a `README.md`.

Sections 1 to 19 also carry a runnable `src/`. The code accumulates section by section.
Each section adds one mechanism and evolves `loop.py`, so a diff between adjacent sections shows what changed.

---

## Running the Demos

Sections 1 to 19 ship runnable demos. Set up once from the repo root:

```bash
uv venv
uv pip install -r requirements.txt
cp .env.example .env        # then add your ANTHROPIC_API_KEY
```

Pinned dependencies are in [`requirements.txt`](requirements.txt). `.env` is gitignored and holds:

- `ANTHROPIC_API_KEY`
- optional `ANTHROPIC_MODEL`
- optional `ANTHROPIC_BASE_URL`

Each runnable section has:

- `test.py`: offline checks, no key needed.
- `demo.py`: live demo against the API.

```bash
python sections/01-agent-loop/src/test.py         # offline
uv run python sections/01-agent-loop/src/demo.py  # live
```

---

## Contributing

- **Add a system.** Slot a new agent into the same section structure.
- **Deepen a section.** Add a mechanism, clearer diagram, or sharper failure mode.
- **Correct the record.** These are reconstructions from source, docs, and behavior. Sourced corrections are welcome.

Favor named, verifiable mechanisms over speculation. Cite sources.

---

## References

| Source | What it offers |
| --- | --- |
| [claude-code](https://github.com/yasasbanukaofficial/claude-code) | Claude Code source backup used for mechanism names and implementation paths. |
| [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | Code-first harness reconstruction and section framing. |
