# 9 · Memory

> Store durable facts outside the conversation.

`messages[]` is memory for one run. It ends with the run and can be compacted during the run.

Long-term memory is different. It stores durable facts outside the conversation, then recalls the relevant ones for a future turn.

Memory must:

1. Decide what is worth saving.
2. Write it outside the conversation.
3. Recall only relevant items.
4. Clean up stale or duplicate items over time.

Without memory, the agent repeats questions and forgets user preferences between sessions. If it saves everything, recall gets noisy and stale.

---

## Mechanism

Memory is a file store plus an index plus on-demand recall.

The loop does not read the whole store. It reads a cheap index, then loads only the few memory files that match the current query.

```mermaid
flowchart TD
    Q([User query]) --> SEL{relevance selector}
    IDX["index: name · type · description"] --> SEL
    SEL -->|top hits| INJ[inject file bodies]
    INJ --> L[(agent loop)]
    L -->|run ends| EX[extract new memories]
    EX --> STORE[(memory dir + index)]
    STORE -.periodically.-> CON[dedupe · merge · prune]
    CON --> STORE
    STORE --> IDX
```

There are four operations:

- **Selection** decides what to save. Save facts that cannot be derived again with grep, git, or project files.
- **Recall** runs at query time. It ranks existing memories and injects only the selected bodies.
- **Extraction** runs at run end. It writes new memory files.
- **Consolidation** runs rarely. It merges duplicates and prunes stale entries.

Recall reads. Extraction writes. Keeping those directions separate avoids accidental store growth.

### New: index, recall, extraction, and the store

The store is a directory of `.md` files. `load_index` reads frontmatter only:

```python
def load_index(memory_dir) -> list[Memory]:            # src/memory.py
    mems = []
    for md in sorted(Path(memory_dir).glob("*.md")):
        if md.name == "MEMORY.md":                     # the index file is not a memory
            continue
        meta, _body = _split(md.read_text())           # frontmatter only, never the body
        mems.append(Memory(md.stem, meta.get("type", ""), meta.get("description", ""), md))
    return mems

def manifest(mems) -> str:                             # one cheap line per memory
    return "\n".join(f"- {m.name} ({m.type}): {m.description}" for m in mems)
```

Recall ranks the index against the query. Offline, the demo uses word overlap. Live, a selector can choose memory names:

```python
def recall(mems, query, k=RECALL_K, selector=None) -> list[Memory]:
    if selector is not None:
        chosen = set(selector(manifest(mems), query))  # live: an LLM returns names to inject
        return [m for m in mems if m.name in chosen][:k]
    scored = ((_overlap(query, m), m) for m in mems)
    hits = sorted((s for s in scored if s[0]), key=lambda s: s[0], reverse=True)
    return [m for _score, m in hits[:k]]
```

Extraction is the only operation that grows the store:

```python
def extract(memory_dir, messages, extractor) -> list[Path]:
    written = []
    for m in extractor(messages) or []:
        path = Path(memory_dir) / f"{m['name']}.md"
        path.write_text(_render(m))
        written.append(path)
    return written
```

`Store` is the handle the loop uses. The selector and extractor are optional, so the tests can run offline.

### How it integrates

Memory wraps the loop on both ends:

```python
if memory is not None:                                 # before the loop
    user_text = messages[-1]["content"]
    recalled = memory.recall(user_text)
    if recalled:
        messages[-1]["content"] = f"<system-reminder>\n{recalled}\n</system-reminder>\n\n{user_text}"
...
if response.stop_reason != "tool_use":
    if memory is not None:
        memory.write(messages)                         # run ends: extract
    return final_text(response)
```

- Recall runs once before the turn and injects selected memory text.
- Extract runs when the model stops without another tool call.
- `memory=None` keeps the section-8 loop behavior.
- Recalled text enters `messages[]`, so context management can later compact it.

---

## Per system

Rows are systems. Columns are the four memory operations.

| System | Store | Recall | Extraction | Consolidation |
| --- | --- | --- | --- | --- |
| **Claude Code** | Markdown files with frontmatter. | Selector chooses a small set. | Forked agent writes memories at run end. | Background process merges and prunes. |

### Claude Code

- Memories live under `~/.claude/projects/<sanitized-git-root>/memory/`.
- Each memory is a `.md` file with YAML frontmatter.
- Memory types include `user`, `feedback`, `project`, and `reference`.
- `MEMORY.md` is an index, not a memory body.
- Recall builds a manifest from names, types, descriptions, and age.
- A Sonnet side query chooses up to 5 memories.
- Bodies are injected with freshness notes.
- Extraction runs as a forked agent at run end.
- Consolidation is the "Dream" background task, gated by time, session count, and a lock.

> **Trade-off:** LLM-based recall can judge relevance better than simple keywords.
> It costs an extra model call.
> A vector store is cheaper at lookup time, but it adds an index to maintain.

---

## Failure modes

- **Recall misses useful memory.** Tune the selector and keep descriptions concrete.
- **Recall floods the turn.** Cap the number of injected memories and prefer precision.
- **Stale memory is treated as fact.** Include age or freshness metadata.
- **Store gets noisy.** Consolidate duplicates and contradictions.
- **Saving derivable facts.** Do not store facts that grep, git, or source files can answer better.
- **Extraction misses details.** Compaction may have removed nuance before extraction. Extract near run end and keep important facts in files.

---

## Runnable

[`src/`](src/) carries 08 forward and adds:

- [`memory.py`](src/memory.py): a `Store`, index loading, recall, and extraction.
- [`loop.py`](src/loop.py): recalls into the opening turn and extracts at run end.
- [`test.py`](src/test.py): walks the four operations on a temporary store.

```bash
python sections/09-memory/src/test.py         # offline checks, no key
uv run python sections/09-memory/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `memdir/findRelevantMemories.ts`, `memdir/memdir.ts`, `services/SessionMemory/sessionMemory.ts`.
- Claude Code memory services: `services/extractMemories/extractMemories.ts`, `services/autoDream/autoDream.ts`.
- learn-claude-code · s09_memory: section framing.
