# 10 · System prompt assembly

> The prompt is built, not written. Each turn concatenates sections chosen from live state.

An agent's system prompt is its standing instructions: who it is, what tools it has, what the project looks like. None of that is a single hardcoded string. It is assembled at runtime from independent sections, each one switched on or off by the real state of the session (which tools are enabled, whether a memory file exists, which mode is active).

---

## Problem

A one-string prompt does not survive contact with a real agent. Once the harness has tools, memory, output styles, and MCP servers, the prompt has to describe whatever is actually live this run.

1. **Drift.** Hand-editing one giant string means new capability text collides with old instructions, and nobody knows which lines are load-bearing.
2. **Waste.** Shipping every clause every turn burns tokens on sections the current session does not use (no MCP server connected, no memory file present).
3. **Cache misses.** If the whole prompt is one blob and any part changes per turn, the entire prefix re-bills instead of hitting the prompt cache.

Leave it hardcoded and the prompt becomes either stale or bloated, and the agent pays for both on every single call.

---

## Mechanism

Define the prompt as a list of named sections. Some are static (always present), some are dynamic (a `compute()` that returns a string or `null`). Resolve them against current state, drop the `null`s, and join. The result is stable across a conversation, so one top-level cache breakpoint caches the whole prompt (and the growing messages with it).

```python
sections = [
    intro, system_rules, doing_tasks, tools_section,   # static
    session_guidance(), memory(), env_info(),          # compute() -> str | None
    output_style(), mcp_instructions(),                # null when not applicable
]
prompt = [s for s in resolve(sections) if s is not None]
# recalled memory bodies (section 9), CLAUDE.md, and date ride as a separate <system-reminder> message
```

Two ideas do the work.

1. A section is included by **state, not keywords**: `mcp_instructions` appears only when an MCP server is connected, `env_info` only when there is a cwd.
2. The prompt is **stable across a conversation**, so one top-level `cache_control` caches it whole along with the growing messages. (Claude Code splits it further at a `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` to protect a large static prefix from a churning tail; below.)

### New: sections and assemble

A `Section` is `static` (returns a constant) or dynamic (`compute(state) -> str | None`):

```python
@dataclass
class Section:                                          # src/prompt.py
    name: str
    compute: Callable    # (state) -> str | None ; static sections ignore state

def static(name, text) -> Section:                     # always present, state-independent
    return Section(name, lambda _state: text)
```

`assemble` is the whole mechanism: run every `compute`, drop the `None`s, and join.

```python
def assemble(sections, state) -> str:                  # the prompt for this turn
    parts = (s.compute(state) for s in sections)
    return "\n\n".join(p for p in parts if p is not None)
```

The section list is where state-driven inclusion lives: a dynamic section returns `None` until its state is present, so `env` appears only with a cwd, `mcp` only when a server is connected. Recalled memory is not here: it rides in the message (section 9), so it never invalidates the system-prompt cache:

```python
DEMO_SECTIONS = [
    static("intro", "You are a tiny agent. ..."),
    Section("tools", lambda s: "Tools: " + ", ".join(s["tools"]) if s.get("tools") else None),
    Section("env", lambda s: f"cwd: {s['cwd']}" if s.get("cwd") else None),
    Section("mcp", lambda s: "MCP servers connected; ..." if s.get("mcp") else None),
]
```

### How it integrates

The loop re-assembles the prompt from live state every turn and passes it to the model, so `model` gains a `system` argument:

```python
for _ in range(max_steps):                             # src/loop.py
    messages = context.manage(messages, summarizer=summarizer)
    system = prompt(registry, session) if prompt else None   # 10 · assemble from live state
    response = model(messages, registry, system)
    ...
```

- `prompt` is a callable closing over the section list; it reads the live registry (enabled tools) and session, so the prompt only ever describes what is actually live this turn.
- Re-running it each turn is cheap, and because the prompt is stable across a conversation the whole thing is cached automatically (the demo enables it), along with the growing messages (section 8).
- Pass `prompt=None` and the loop sends `system=None`, falling back to the section-9 behavior.

### Prompt caching: one automatic breakpoint

A conversation's system prompt barely moves (tools, cwd, MCP servers are stable per session); what grows is `messages[]`. So the demo sets one top-level `cache_control`. The API caches up to the last block and advances the breakpoint as messages grow:

```python
client.messages.create(model=MODEL, system=assemble(DEMO_SECTIONS, state),   # src/demo.py
                       messages=messages, cache_control={"type": "ephemeral"})  # caches system + messages
```

- A cache write costs ~1.25x a base input token, a read ~0.1x: after the first call, the prefix re-reads at a tenth of the price.
- Order is tools, then system, then messages; a change invalidates that level and everything after. So volatile content goes last: recalled memory rides in the message (section 9), busting only the messages cache.
- Ephemeral, 5-minute sliding TTL (1-hour available). Under the per-model minimum (1024 tokens, 2048 for Haiku) nothing caches, so the tiny demo shows placement, not a live hit.

Claude Code adds an explicit breakpoint at `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` so a churning tail recomputes without rewriting its large static prefix; the two compose. The strip-down's prompt is small and stable, so one automatic breakpoint covers it.

---

## Per system

How the prompt is composed each turn, where it happens, and from what.

| System | Assembly point | Sections | When built |
| --- | --- | --- | --- |
| **Claude Code** | `getSystemPrompt()` (`constants/prompts.ts`), via `QueryEngine.ts` | 7 static + 7 dynamic (`systemPromptSection`), split at `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` | Per turn from live state; CLAUDE.md + date go in a separate `<system-reminder>` |
| *(more soon)* | | | |

### Claude Code

- **Output.** Assembly returns a `string[]`, one element per section.
- **Tool guidance tracks reality.** `getUsingYourToolsSection(enabledTools)` writes from the registered set, so the prompt names only tools that exist.
- **Dynamic sections are memoized.** `resolveSystemPromptSections` caches each `compute()` in `STATE.systemPromptSectionCache` until `/clear` or `/compact` calls `clearSystemPromptSections`.
- **MCP opts out.** `mcp_instructions` uses `DANGEROUS_uncachedSystemPromptSection`: servers connect and disconnect between turns, so it must recompute.
- **Context is separate.** CLAUDE.md and `currentDate` are not in the array; `getUserContext` returns them, `utils/api.ts` wraps them in a `<system-reminder>` message, and `getSystemContext` adds `gitStatus`.

> **Trade-off:** splitting the prompt into state-driven sections behind a cache boundary buys cheap edits, no token waste on absent features, and a stable cacheable prefix. It costs real machinery (a section registry, a cache, a boundary marker, ordering rules) and the discipline to mark volatile sections explicitly so one changing value does not bust the whole prefix.

---

## Failure modes

- **Cache-busting volatility.** A volatile section before the breakpoint rewrites the whole prefix at 1.25x. Mitigation: keep it in the tail, marked `DANGEROUS_uncachedSystemPromptSection` (section 8).
- **Stale section cache.** Memoized sections keep returning old values after state changes. Mitigation: invalidate on `/clear` and `/compact` (`clearSystemPromptSections`).
- **Tool text without the tool.** Naming a tool the session never enabled confuses the model. Mitigation: gate guidance on the live `enabledTools` set (section 2).
- **Context vs prompt confusion.** CLAUDE.md or git status in the system prompt busts the shared prefix every project and day. Mitigation: inject it as a `<system-reminder>` message instead (section 9).
- **Mode collisions.** Override, agent, and custom prompts all fight to replace the default. Mitigation: one resolver (`buildEffectiveSystemPrompt`) sets the priority order (section 6).

---

## Runnable

[`src/`](src/) carries 09 forward and adds:

- [`prompt.py`](src/prompt.py): `Section`s (static or `compute(state) -> str | None`) and `assemble` (run each, drop `None`s, join).
- [`loop.py`](src/loop.py): re-assembles the prompt each turn.
- [`demo.py`](src/demo.py): adds a top-level `cache_control` to cache the prompt with the growing messages.
- [`test.py`](src/test.py): checks state-driven inclusion.

```bash
python sections/10-system-prompt/src/test.py         # offline checks, no key
uv run python sections/10-system-prompt/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `constants/prompts.ts`, `constants/systemPromptSections.ts`, `utils/api.ts`, `QueryEngine.ts`.
- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching): `cache_control` breakpoints, pricing, TTLs, token minimums.
- learn-claude-code · s10_system_prompt: section framing.

Educational reconstruction from public structure and observed behavior, not an official description of any system.
