"""Section 15 demo: a real turn bound to its own git worktree. The model uses
the shell to write a file; the write lands inside the worktree, never in the
main tree. The concurrent no-clobber case is proven offline in test.py.

We create a worktree, then run one turn inside `cwd_override`: every tool that
reads get_cwd() (here the Bash tool) resolves paths in the worktree, so the
model's `> notes.txt` lands there. The loop and the subagent path are unchanged
(section 14 kept the loop too); isolation wraps a unit of work from outside by
binding its cwd. On teardown the worktree has changes, so it is kept for review.

Runs in a throwaway temp git repo, so it never touches this checkout.

    uv run python sections/15-worktree-isolation/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import subprocess
import tempfile
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

import worktree
from loop import Session, run_turn
from permissions import DEFAULT
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = "You are a tiny agent working in an isolated checkout. Use the shell when asked, then answer in one line."


def _init_repo(root):
    def g(*a):
        subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (Path(root) / "config.py").write_text("shared = 1\n")
    g("add", "."); g("commit", "-q", "-m", "init")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("15 worktree isolation: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system or SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=512)

    def sh(a):                                             # a real tool resolves paths in the bound cwd
        return subprocess.run(a["command"], shell=True, capture_output=True, text=True,
                              timeout=60, cwd=worktree.get_cwd()).stdout.strip()

    with tempfile.TemporaryDirectory() as repo:
        _init_repo(repo)
        reg = Registry()
        reg.register(Tool("Bash", sh, description="Run a shell command.",
                          input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                                        "required": ["command"]}))
        session = Session(mode=DEFAULT, allow_rules={"Bash"})

        wt = worktree.create(repo, "agent-1")              # isolated checkout, own branch
        print("15 worktree isolation: created worktree", wt.name, "- running a turn inside it...")

        with worktree.cwd_override(wt):                    # bind this unit of work to its worktree
            out = run_turn([{"role": "user", "content":
                             "Using the shell, write the word ISOLATED into a file named notes.txt, then report done."}],
                           model, reg, session)
        print("15 worktree isolation -> turn:", out)

        landed = (wt / "notes.txt").exists()
        main_clean = not (Path(repo) / "notes.txt").exists()
        print(f"15 worktree isolation: notes.txt in worktree={landed}, main tree untouched={main_clean}")

        removed = worktree.remove(repo, "agent-1")         # has changes, so kept for review
        print(f"15 worktree isolation: auto-removed={removed} (kept-for-review, the worktree has changes)")


if __name__ == "__main__":
    demo()
