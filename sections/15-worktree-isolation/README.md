# 15 · Worktree isolation

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

> Give parallel agents separate working directories.

A single working directory is shared mutable state. If two agents write the same file at the same time, one can overwrite the other's work.

The task system decides what work exists. Subagents decide how work is split. Worktree isolation decides where file writes happen.

Each unit of work gets its own checkout and branch. The agent's file and shell tools resolve paths inside that checkout.

The isolation layer must:

1. Create a private checkout for each unit of work.
2. Bind tools to that checkout.
3. Reject names that would escape the worktree root.
4. Remove clean worktrees and keep dirty ones for review.

Without this layer, parallel writers can corrupt the shared tree.

---

## Mechanism

There are two pieces:

1. A private git worktree per unit of work.
2. A per-context working-directory binding.

The binding must be scoped to the agent context. A global `chdir` would affect other agents in the same process.

```mermaid
flowchart TB
    T["unit of work · slug"] --> V["validate slug"]
    V --> W["git worktree add · own branch"]
    W --> B["bind cwd to this context"]
    B --> R["agent loop · tools resolve in worktree"]
    R --> C{"changes?"}
    C -->|none| X["auto-remove"]
    C -->|"changes"| K["keep for review"]
```

- Each worktree is a checkout of the same repo on its own branch.
- The slug becomes a path, so validate it before any path join.
- Tools read `get_cwd()` from context, not from a global process cwd.
- Teardown removes only clean worktrees. Dirty worktrees stay for review.

### New: the worktree and cwd binding

`worktree.py` validates a slug, creates a worktree, and binds cwd through a context variable:

```python
_cwd = contextvars.ContextVar("cwd", default=None)   # per-context cwd

@contextlib.contextmanager
def cwd_override(path):
    token = _cwd.set(str(path))                       # bind, never os.chdir
    try:
        yield
    finally:
        _cwd.reset(token)

def remove(repo_root, slug, force=False):
    path = _path(repo_root, slug)                     # _path validates the slug first
    if not force and changes(path):
        return False                                  # keep for review
    _git(repo_root, "worktree", "remove", "--force", str(path))
    _git(repo_root, "branch", "-D", f"worktree-{slug}")
    return True
```

- `cwd_override` affects only the current context.
- Tools pass `get_cwd()` to subprocesses and file operations.
- `create` runs `git worktree add -B worktree-<slug>`.
- `validate_slug` rejects traversal and disallowed characters.
- `remove` refuses to remove a dirty worktree unless forced.

### How it integrates

Isolation wraps a turn from outside the loop:

```python
wt = worktree.create(repo, "agent-1")                 # src/demo.py
with worktree.cwd_override(wt):
    run_turn([{"role": "user", "content": prompt}], model, reg, session)
worktree.remove(repo, "agent-1")                       # clean -> remove, dirty -> keep
```

The loop and subagent path do not need special logic. Only the working directory seen by tools changes.

To make this model-selectable, add an `isolation` option to the `Agent` tool schema and branch in `spawn`.

---

## Per system

How each system isolates parallel work and cleans it up.

| System | Isolation unit | Binding | Cleanup |
| --- | --- | --- | --- |
| **Claude Code** | Git worktree per task or session. | Scoped cwd for subagents; process cwd for session mode. | Remove clean worktrees. Keep dirty ones. |

### Claude Code

- `utils/worktree.ts` validates slugs and creates or removes worktrees.
- Worktrees live under `.claude/worktrees/<slug>`.
- Branches are named `worktree-<slug>`.
- `AgentTool` can use `isolation: 'worktree'`.
- Subagents use `runWithCwdOverride` and `AsyncLocalStorage`.
- Session-level worktree mode uses `process.chdir`.
- `ExitWorktreeTool` refuses dirty teardown unless `discard_changes` is true.
- A periodic sweep removes old ephemeral `agent-*` worktrees.
- Task records do not store the worktree binding. The binding lives in cwd scope.

> **Trade-off:** Worktrees give real filesystem isolation and clean diffs.
> They cost disk, setup time, and a later merge step.
> A shared directory is simpler but cannot safely support parallel writers.

---

## Failure modes

- **Path traversal in slug.** Validate before path joins or git commands.
- **Silent loss on remove.** Keep dirty worktrees unless the user explicitly discards changes.
- **cwd leak across agents.** Use context-local cwd for concurrent subagents.
- **Stale worktree buildup.** Sweep only known ephemeral worktrees.
- **Stale reads after fork.** Tell forked children to re-read files inside the worktree.

---

## Runnable

[`src/`](src/) carries 14 forward and adds:

- [`worktree.py`](src/worktree.py): slug validation, worktree creation, context-local cwd, and safe removal.
- [`test.py`](src/test.py): checks two isolated writers and the clean/dirty removal gate.
- [`demo.py`](src/demo.py): runs a live turn inside a worktree.

The loop and subagent path are unchanged. Isolation wraps the turn by binding cwd.

```bash
python sections/15-worktree-isolation/src/test.py         # offline checks, real git, no key
uv run python sections/15-worktree-isolation/src/demo.py  # live demo, needs a key
```

---

## Sources

- Claude Code source: `tools/EnterWorktreeTool/`, `tools/ExitWorktreeTool/`, `utils/worktree.ts`, `utils/cwd.ts`, `tools/AgentTool/AgentTool.tsx`.
- learn-claude-code · s18_worktree_isolation: section framing.
