# 2 · Tool runtime

> Adding a tool means adding one handler. The loop never moves.

The agent loop (section 1) can only act through tools. The tool runtime is the plumbing that turns a model-emitted `tool_use` block into a real action: it advertises what tools exist, validates and routes each call to its handler, runs independent calls in parallel, and feeds the result back. Capability grows by registering handlers, not by editing the loop.

---

## Problem

A model can ask to "read a file" or "run a command," but a model call only emits structured `tool_use` blocks with a `name` and an `input`. Something has to map that name to code, check the input is well formed, execute it, and return a result the model can read.

So the runtime must:

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
    is_read_only: bool = False
    is_concurrency_safe: bool = False         # may batch in parallel
    is_edit: bool = False                     # read by the gate (section 3)

class Registry:                              # src/tools.py
    def register(self, tool): self._tools[tool.name] = tool   # add a handler
    def get(self, name):      return self._tools.get(name)    # dispatch = lookup
```

- A tool is a dataclass; the registry is `name -> tool`; `register` is one line. Adding a capability is registering a handler.
- `run_concurrently` ([`src/tools.py`](src/tools.py)) batches the safe calls: `safe = [i for i, t in enumerate(tools) if t.is_concurrency_safe]` run in one `ThreadPoolExecutor`, the rest in order, so reads parallelize but writes stay sequenced.

### How it integrates

Section 1 ran `run_tool(call)` against an inline `TOOLS` dict. The loop now takes a `registry` and routes each call through `_dispatch`:

```python
def run(user_intent, model, registry, max_steps=10):   # src/loop.py (now takes a registry)
    ...
    for call in reply["tool_calls"]:
        messages.append(_dispatch(call, registry))      # was: run_tool(call)

def _dispatch(call, registry):               # resolve, run, wrap as a tool message
    tool = registry.get(call["name"])         # name -> tool
    return {"role": "tool", "name": call["name"], **run_tool(tool, call.get("args", {}))}
```

- The loop body is otherwise unchanged from section 1; only the dispatch step is now a registry lookup.
- `_dispatch` is the seam sections 3 and 4 grow: the gate and the hooks splice into exactly this function.

The bare loop dispatches sequentially for clarity; `run_concurrently` is the batching primitive a real runtime applies. When a catalog grows large, Claude Code also ships most tools as names only and fetches schemas on demand (`ToolSearchTool`); the demo keeps every tool in hand.

---

## Per system

How each agent defines a tool, routes a call, parallelizes, and keeps a large catalog discoverable.

| System                | Tool definition                                                                                    | Dispatch                                                                                                            | Parallel calls                                                                                                                                                                          | Discovery                                                                                                                                   |
| --------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Claude Code** | `buildTool({...})` object: `name`, `inputSchema` (Zod), `call()`, predicates (`Tool.ts`) | `findToolByName(tools, name)` lookup over the `getAllBaseTools()` registry (`tools.ts`, `toolExecution.ts`) | `partitionToolCalls` batches consecutive `isConcurrencySafe` calls, cap `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY` (default 10); unsafe calls run serially (`toolOrchestration.ts`) | deferred tools ship as names only (`shouldDefer`), model fetches schemas via `ToolSearchTool` (`select:` or keyword + `searchHint`) |
| *(more soon)*       |                                                                                                    |                                                                                                                     |                                                                                                                                                                                         |                                                                                                                                             |

Claude Code's tools are objects built by `buildTool`, which fills safe defaults (`isConcurrencySafe` defaults to `false`, `isReadOnly` to `false`, `checkPermissions` to allow). `getAllBaseTools()` is the single source of truth that lists `BashTool`, `FileReadTool`, `FileEditTool`, `GrepTool`, `AgentTool`, and the rest; `getTools()` and `assembleToolPool()` filter that list by permission rules and merge in MCP tools. Dispatch is `findToolByName`, which also matches `aliases`. Within a turn, `partitionToolCalls` walks the calls in order and groups runs of concurrency-safe ones into a parallel batch (`runToolsConcurrently`), breaking the batch whenever an unsafe call appears so it runs alone. When the catalog grows (many MCP servers), tools marked `shouldDefer` are sent with `defer_loading: true` (names only) and the model calls `ToolSearchTool` to pull full schemas, by exact name (`select:A,B`) or keyword scored against each tool's `searchHint` and description.

> **Trade-off:** a schema-per-tool object model with predicates buys per-tool validation, permission hooks, parallel-safe batching, and lazy discovery, but every tool now carries a contract (schema, concurrency predicate, permission check, render methods). A single `bash` tool has none of that overhead and nothing to register, at the cost of no validation, no parallelism, and no way to gate a destructive command differently from a read.

---

## Failure modes

- **Unknown tool name.** The model emits a `name` with no registered handler (typo, a tool disabled by permissions, or a deferred tool never loaded). Dispatch returns nothing and the call must error back as a result, not crash the loop; Claude Code retries `findToolByName` against the full base set as a fallback.
- **Schema drift.** The advertised `inputSchema` and what `call()` expects diverge, so valid-looking input fails at runtime. Validating against the schema before dispatch (Zod parse) catches it early and returns a model-readable error instead of a thrown exception.
- **Unsafe parallelism.** Two writes to the same file run concurrently and corrupt state. The fix is conservative `isConcurrencySafe` (default `false`, and `false` on any parse failure) so only provably independent calls batch together (relates to permissions, section 3).
- **Catalog overflow.** Dozens of MCP tools blow the prompt's token budget and degrade tool selection. Deferred loading plus `ToolSearchTool` keeps only names in-context until a tool is actually needed (relates to context management, section 8).
- **Oversized results.** A tool returns megabytes and floods the context window. Each tool sets `maxResultSizeChars`; results over the cap are persisted to disk and the model gets a preview plus a path (set to `Infinity` for `FileReadTool` to avoid a read-persist-read loop).

---

## Runnable

[`src/`](src/) is section 1's loop plus the tool runtime. New this section: [`tools.py`](src/tools.py) (Tool, Registry, `run_concurrently`). Updated: [`loop.py`](src/loop.py) now dispatches through a Registry. Stubbed model, no API key.

```
python sections/02-tool-runtime/src/demo.py
```

---

## Sources

- Claude Code structure: `Tool.ts` (`buildTool`, `Tool` type, `inputSchema`, `isConcurrencySafe`, `isReadOnly`, `checkPermissions`, `shouldDefer`, `searchHint`, `maxResultSizeChars`, `findToolByName`), `tools.ts` (`getAllBaseTools`, `getTools`, `assembleToolPool`), `tools/` (`BashTool`, `FileReadTool`, `FileEditTool`, `GrepTool`, `AgentTool`, `ToolSearchTool`), `tools/ToolSearchTool/ToolSearchTool.ts`, `tools/shared/`, `tools/utils.ts`, `services/tools/toolOrchestration.ts` (`partitionToolCalls`, concurrency cap), `services/tools/toolExecution.ts` (`runToolUse` dispatch).
- Framing: learn-claude-code · s02_tool_use

Educational reconstruction from public structure and observed behavior, not an official description of any system.
