# 2 · Tool runtime

> Adding a tool means adding one handler. The loop never moves.

The agent loop (section 1) can only act through tools. A model can ask to "read a file" or "run a command," but a model call only emits structured `tool_use` blocks with a `name` and an `input`; something has to map that name to code, check the input is well formed, execute it, and return a result the model can read. That plumbing is the tool runtime, and capability grows by registering handlers, not by editing the loop. So the runtime must:

1. Tell the model which tools exist and what arguments each takes (schemas).
2. Route a `tool_use` block by `name` to the right handler (dispatch).
3. Run multiple calls in one turn without serializing safe ones needlessly (parallelism).
4. Keep the catalog usable as it grows past what fits in one prompt (discovery).

Leave it out and the model can reason about acting but has no way to act. Hard-wire one tool (just `bash`) and every new capability becomes a string-templating chore, with no per-tool validation, permissions, or parallelism.

---

## Mechanism

A tool is a small self-describing object: a `name`, a `run` handler, and predicates the runtime queries (`is_read_only`, `is_concurrency_safe`, `is_edit`). A `Registry` collects them by name, and dispatch is a dict lookup, not a `switch`.

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

- A tool is a dataclass; the registry is `name -> tool`; `register` is one line. Adding a capability is registering a handler.
- `run_concurrently` ([`src/tools.py`](src/tools.py)) batches the safe calls: `safe = [i for i, t in enumerate(tools) if t and t.is_concurrency_safe]` run in one `ThreadPoolExecutor`, the rest in order, so reads parallelize but writes stay sequenced.

### How it integrates

Section 1 ran tools from an inline `HANDLERS` dict. The loop now takes a `registry` and routes each `tool_use` block through `_dispatch`:

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

- The loop body is otherwise unchanged from section 1; only the dispatch step is now a registry lookup.
- `_dispatch` is the seam sections 3 and 4 grow: the gate and the hooks splice into exactly this function.

The bare loop dispatches sequentially for clarity; `run_concurrently` is the batching primitive a real runtime applies. When a catalog grows large, Claude Code also ships most tools as names only and fetches schemas on demand (`ToolSearchTool`); the demo keeps every tool in hand.

---

## Per system

How each agent defines a tool, routes a call, parallelizes, and keeps a large catalog discoverable.

| System | Tool definition | Dispatch | Parallel calls | Discovery |
| --- | --- | --- | --- | --- |
| **Claude Code** | `buildTool({...})`: `name`, `inputSchema` (Zod), `call()`, predicates (`Tool.ts`) | `findToolByName` over the `getAllBaseTools()` registry (`toolExecution.ts`) | `partitionToolCalls` batches `isConcurrencySafe` runs, cap 10 (`CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY`); unsafe run serially | deferred tools ship as names (`shouldDefer`); model pulls schemas via `ToolSearchTool` (`select:` or keyword + `searchHint`) |
| *(more soon)* | | | | |

### Claude Code

- **Safe defaults.** `buildTool` fills them: `isConcurrencySafe` and `isReadOnly` default to `false`, `checkPermissions` to allow.
- **One source of truth.** `getAllBaseTools()` lists `BashTool`, `FileReadTool`, `FileEditTool`, `GrepTool`, `AgentTool`, and the rest; `getTools()` and `assembleToolPool()` filter by permission rules and merge in MCP tools.
- **Dispatch.** `findToolByName` resolves by `name`, also matching `aliases`.
- **Parallel batching.** `partitionToolCalls` walks calls in order, groups concurrency-safe runs into a parallel batch (`runToolsConcurrently`), and breaks the batch at any unsafe call so it runs alone.
- **Lazy discovery.** Tools marked `shouldDefer` ship with `defer_loading: true` (names only); the model calls `ToolSearchTool` to pull full schemas, by exact name (`select:A,B`) or keyword scored against each tool's `searchHint` and description.

> **Trade-off:** a schema-per-tool object model with predicates buys per-tool validation, permission hooks, parallel-safe batching, and lazy discovery, but every tool now carries a contract (schema, concurrency predicate, permission check, render methods). A single `bash` tool has none of that overhead and nothing to register, at the cost of no validation, no parallelism, and no way to gate a destructive command differently from a read.

---

## Failure modes

- **Unknown tool name.** The model emits a `name` with no registered handler (typo, disabled, or a deferred tool never loaded). Mitigation: error back as a `tool_result` instead of crashing the loop; Claude Code retries `findToolByName` against the full base set.
- **Schema drift.** The advertised `inputSchema` and what `call()` expects diverge, so valid-looking input fails at runtime. Mitigation: validate against the schema before dispatch (Zod parse), returning a model-readable error.
- **Unsafe parallelism.** Two writes to the same file run concurrently and corrupt state. Mitigation: conservative `isConcurrencySafe` (default `false`, and `false` on any parse failure) so only provably independent calls batch (section 3).
- **Catalog overflow.** Dozens of MCP tools blow the token budget and degrade tool selection. Mitigation: deferred loading plus `ToolSearchTool` keeps only names in-context until a tool is needed (section 8).
- **Oversized results.** A tool returns megabytes and floods the context window. Mitigation: each tool sets `maxResultSizeChars`; over-cap results persist to disk and the model gets a preview plus a path (`Infinity` for `FileReadTool` avoids a read-persist-read loop).

---

## Runnable

[`src/`](src/) carries 01 forward and adds:

- [`tools.py`](src/tools.py): `Tool`, `Registry`, and `run_concurrently` (batch the concurrency-safe calls).
- [`loop.py`](src/loop.py): dispatches each `tool_use` through the `Registry` (`_dispatch`); the model advertises `registry.schemas()`.
- [`demo.py`](src/demo.py): live entry; registers a `ReadFile` tool and runs the loop against the API.
- [`test.py`](src/test.py): offline checks for dispatch, the unknown-tool error, and parallel batching.

```bash
python sections/02-tool-runtime/src/test.py         # offline checks, no key
uv run python sections/02-tool-runtime/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `Tool.ts`, `tools.ts`, `services/tools/toolOrchestration.ts`, `services/tools/toolExecution.ts`, `tools/ToolSearchTool/ToolSearchTool.ts`.
- learn-claude-code · s02_tool_use: section framing.
