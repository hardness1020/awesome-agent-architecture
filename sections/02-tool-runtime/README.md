# 2 · Tool runtime

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> Adding a capability means registering a tool. The loop stays the same.

The agent loop can only act through tools. The model emits a structured `tool_use` block with a `name` and an `input`.

The harness maps that name to code. It validates the input, runs the handler, and returns a result.

The runtime must:

1. Tell the model which tools exist.
2. Describe each tool's input schema.
3. Route each `tool_use` by name.
4. Run safe calls in parallel when possible.
5. Keep large tool catalogs discoverable.

Without this layer, the model can ask to act but nothing can execute the action.

With only one `bash` tool, every capability becomes string handling. There is no per-tool validation or permission logic.

Two failures start here and get blamed on the model. It picks the wrong tool because two descriptions overlap. An edit fails because the harness rewrote the input.

---

## Mechanism

![Mechanism diagram](assets/02-tool-runtime.png)

A tool is a small object with a name, a handler, a schema, and a few predicates. A registry stores tools by name. Dispatch is a lookup.

### New: the tool runtime

```python
@dataclass
class Tool:                                  # src/tools.py
    name: str
    run: Callable[[dict], Any]
    description: str = ""                      # advertised to the model
    input_schema: dict = ...                   # the Anthropic schema it accepts
    is_read_only: bool = False
    is_concurrency_safe: bool = False         # may batch in parallel
    is_edit: bool = False                     # read by the gate (section 3)

class Registry:                              # src/tools.py
    def register(self, tool): self._tools[tool.name] = tool   # add a handler
    def get(self, name):      return self._tools.get(name)    # dispatch = lookup
    def schemas(self):        ...             # the tools list handed to the model
```

- A tool is a dataclass.
- The registry is `name -> tool`.
- Adding a capability means registering one handler.
- `schemas()` returns the tool list advertised to the model.
- `run_concurrently` batches tools marked `is_concurrency_safe`.
- Unsafe calls stay in order, so writes do not race.

### How it integrates

Section 1 used an inline `HANDLERS` dict. Section 2 passes a `registry` into the loop and routes each `tool_use` through `_dispatch`:

```python
def run_turn(messages, model, registry, max_steps=10): # src/loop.py (now takes a registry)
    ...
    results = [_dispatch(b, registry)                   # was: run_tool(call)
               for b in response.content if b.type == "tool_use"]
    messages.append({"role": "user", "content": results})

def _dispatch(block, registry):              # resolve, run, wrap as a tool_result
    tool = registry.get(block.name)           # name -> tool
    content = run_tool(tool, block.input)
    return {"type": "tool_result", "tool_use_id": block.id, "content": content}
```

The loop body is otherwise unchanged. Only the dispatch step now uses the registry.

`_dispatch` is the next extension point. Section 3 adds the permission gate there. Section 4 adds hooks there.

The demo dispatches sequentially for clarity. Real runtimes batch safe calls and load large tool schemas on demand.

### Further reading

The designs below are not in `src/`. They come from ai-agent-book's account of how production agents are built, and from published work on tool use.
Read them as reported design, not as confirmed behavior of the systems in the table below.
Where Claude Code is named, the contrast comes from its own source, cited at the end.

**Grouping.** A flat registry hides the shape of a catalog. Tools fall into five groups, by where a call goes and what it touches.
Perception reads the outside world. Execution changes it. Collaboration reaches another agent. An event trigger lets the outside world wake the agent.
User communication reaches the person. Sections 6, 12, and 16 build the collaboration group. Sections 13 and 14 build the event triggers.
Section 19 builds the user channel. This section builds the layer all five sit on.

**Granularity.** Merge two tools when they do the same kind of work on the same kind of input. One `read_document` with a type parameter beats one reader per file format.
Split them when the parameters stop overlapping. A schema that unions unrelated fields cannot say which fields apply, so the model fills the wrong ones.

**Description craft.** `description` is not documentation. It is the only thing the model reads before it picks. A good one says when to use the tool and when not to.
It gives real parameter values, shows what comes back, and says what a call costs. A few worked examples help more than another paragraph of prose.
The book reports a large gain from adding examples. That figure has no citation, so take the direction and not the size.

**Parameter fidelity.** The harness has to hand the input to the handler unchanged. Say it normalizes a quote character, trims whitespace,
or adds an argument the model never wrote. The call then fails for a reason the model cannot see. It sent the right input.
The result says the edit did not match. Nothing in the transcript explains the gap. Reject bad input and say why. Do not rewrite it.

**Checklist parameters.** Some parameters exist to be ignored. A parameter like `expected_price` makes the model write down what it believes before the call runs.
The handler does not act on that number. It reads the stored value, decides on that, and logs the two when they differ.
The last check then stands on data the model cannot forge. τ-bench scores runs the same way. It reads the final database state, not what the agent said it did.

**Perception interfaces.** A perception tool usually finds more than fits in the context. Three rules keep the result honest.
Search returns one page of candidates plus a cursor. A read takes an offset and a limit, so the model can walk a long file. Truncation is labeled in the result.
A silent cut is worse than an error, because the model then reads a partial file as if it were whole.

Code search shows the choice. Four approaches, and no system uses only one:

| Approach | Finds | Cost |
| --- | --- | --- |
| **Glob** | Files by path pattern. | Nothing about content. |
| **Grep** | Exact strings and regexes, with line numbers. | Several calls to narrow a query. Misses synonyms. |
| **Embedding index** | Code by meaning, so a plain-language query lands. | An index to build and keep in sync. Opaque ranking. |
| **LSP symbols** | Definitions, references, and types, exactly. | A language server per language. |

Claude Code ships no index. It searches step by step: glob, then grep, then read, and the model narrows the query between calls.
The book describes Cursor taking the other route, paying to build an index so that a plain-language query can find code that names no identifier.

Editing splits the same way. Five ways to say what changed:

| Scheme | The model emits | Trade-off |
| --- | --- | --- |
| **Diff plus apply model** | A rough skeleton diff, rewritten by a second trained model. | Fast and forgiving. Needs that second model. |
| **Old and new string** | The exact text to find and the text to put in its place. | Unambiguous, and fails loudly. Needs a fresh read first. |
| **Line numbers** | A range and its replacement. | Compact. Stale once an earlier edit shifts the file. |
| **Editor commands** | A small command language, vim style. | Terse. One more syntax to get wrong. |
| **Anchors** | A start marker and an end marker. | Survives shifts. Ambiguous when the marker repeats. |

Claude Code replaces an exact old string and makes the model read the file first, so a stale string fails loudly instead of editing the wrong line.
The book describes Cursor sending a rough skeleton instead, with a second trained model rewriting the file from it, and reports that route as the faster one.

**Early start and cascade abort.** Batching is not the only way to overlap work. A call can start the moment its own arguments finish parsing,
while the model is still writing the rest of the batch. That hides the call's latency inside generation. It needs one rule for failure:
an error stops the calls that depended on it. Independent calls in the same batch keep running, and so does the parent turn.

**Shell state.** Two designs, both defensible.

- **Reset per call.** Claude Code's bash tool does not keep a live shell between calls. Environment variables and shell functions set in one call are gone by the next,
  and the tool description tells the model to use absolute paths. Each call reproduces on its own, and parallel calls cannot leak into each other.
- **One persistent session.** The book makes a shared terminal the default. `cd`, exported variables, and an activated virtual environment all survive.
  Separate shells stay available for parallel work. The model repeats fewer setup commands. The harness gains session state to track and reset.

**Discovery at scale.** A big catalog cannot ship in full, so the registry sends names first and loads a full schema when something asks for it.
The ask can come from the model, in plain language. MCP-Zero has the agent say which capability it is missing, matches that to a server, then to a tool on that server,
and injects only the matched schema. The model never had to know the tool existed, which is the part a keyword search cannot do.

**Cache-safe loading.** Where the schema lands matters. Append it once, at the end of the context, and leave it there.
Editing the tool block at the front of the prompt invalidates the cached prefix and every token after it (section 10).
Appending leaves the prefix alone, and the schema turns into ordinary history on the next turn.

---

## Per system

How each agent defines tools, routes calls, handles parallelism, and exposes a large catalog.

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | Per-tool validation, permissions, safe parallelism, and lazy discovery. | One `bash` tool keeps the runtime small. No catalog to manage. |
| **Cons** | Every tool has to carry a contract. | No per-tool validation or permissions. The confirm gate (section 3) sees only a command string. |
| **Why** | Adding a capability should mean registering a tool, with the loop unchanged. | Assumes every action can be a shell command, so one tool is enough. |
| **How: tool definition** | Schema, handler, and predicates. | One hardcoded `bash` schema is the whole catalog: one command field. Any other name is an error. |
| **How: dispatch** | Name lookup with aliases, over a permission-filtered pool with MCP tools. | No registry. Every call is a shell command. |
| **How: parallel calls** | Safe calls batch. Unsafe calls run alone. Safety flags default to off. | No. The legacy text mode requires exactly one action per response. |
| **How: discovery** | Names ship first. Full schemas load on request, by exact name or keyword. | Not needed with one tool. |

---

## Failure modes

- **Unknown tool name.** The model names a missing or disabled tool. Return a `tool_result` error instead of crashing the loop.
- **Schema drift.** The schema says one thing and the handler expects another. Validate before dispatch.
- **Unsafe parallelism.** Two writes can corrupt the same file. Default to serial execution unless a tool is known to be safe.
- **Catalog overflow.** Too many tool schemas can crowd the prompt. Defer full schemas until needed, and append a loaded schema at the end so the cached prefix survives.
- **Oversized results.** Large outputs can fill the context window. Cap results, persist the full output, and return a preview plus a path.
  Label the cut. A silent one leaves the model reading a partial file as if it were whole.
- **Wrong tool picked.** Two descriptions overlap, or one tool does two jobs. Merge duplicates, split overloaded schemas, and say what each tool is not for.
- **Silent input drift.** The harness normalizes or adds an argument on the way to the handler. The call fails and the model cannot tell why. Reject bad input with a reason.
- **Batch failure spreads.** One failed call in a parallel batch kills the whole turn. Abort only the calls that depended on it.

---

## Runnable

[`src/`](src/) carries 01 forward and adds:

- [`tools.py`](src/tools.py): `Tool`, `Registry`, and `run_concurrently`.
- [`loop.py`](src/loop.py): dispatches each `tool_use` through the `Registry`.
- [`demo.py`](src/demo.py): registers a `ReadFile` tool and runs the loop against the API.
- [`test.py`](src/test.py): checks dispatch, unknown-tool errors, and parallel batching.

```bash
python sections/02-tool-runtime/src/test.py         # offline checks, no key
uv run python sections/02-tool-runtime/src/demo.py  # live demo, needs a key
```

---

## Sources

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code):
  `Tool.ts`, `tools.ts`, `services/tools/toolOrchestration.ts`, `services/tools/toolExecution.ts`, `tools/ToolSearchTool/ToolSearchTool.ts`.
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent): `models/utils/actions_toolcall.py`, `models/utils/actions_text.py`, `environments/__init__.py`.
- [learn-claude-code · s02_tool_use](https://github.com/shareAI-lab/learn-claude-code): section framing.
- [ai-agent-book](https://github.com/bojieli/ai-agent-book): `book/chapter4.md`, `book/chapter5.md` (《深入理解 AI Agent》, 李博杰; the Chinese original is canonical):
  the five-tool grouping, granularity, description craft, parameter fidelity, perception interface rules, proactive discovery, cache-safe loading, streaming tool start
  with cascade abort, the persistent shell default, the search and edit comparisons, and checklist parameters.
  Its Claude Code and Cursor readings are the author's own source study of fast-moving implementations, so read them as period evidence.
- [MCP-Zero](https://arxiv.org/abs/2506.01056) (Fei et al.): the agent declares a capability gap, and matching runs server first, then tool.
- [τ-bench](https://arxiv.org/abs/2406.12045) (Sierra): success judged against the final database state, which is what checklist parameters lean on.
