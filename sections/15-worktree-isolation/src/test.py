"""Section 15 offline checks: slug validation rejects traversal, a real git
worktree is created and torn down, the clean/dirty gate keeps work, and two
threads each bound to their own worktree never clobber each other. Uses real git
in a temp repo. No key, no network.

    python sections/15-worktree-isolation/src/test.py
"""
import subprocess
import tempfile
import threading
from pathlib import Path

import worktree


def _init_repo(root):
    def g(*a):
        subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (Path(root) / "config.py").write_text("shared = 1\n")
    g("add", "."); g("commit", "-q", "-m", "init")


def _write_in_cwd(path, name, body):
    # honors the bound cwd like a real tool would (subprocess cwd=get_cwd())
    with worktree.cwd_override(path):
        subprocess.run(["sh", "-c", f"printf '%s' '{body}' > {name}"],
                       cwd=worktree.get_cwd(), check=True)


def test():
    # slug validation runs at the boundary, before any git command
    for bad in (".", "..", "../target", "a/b", "", "x;rm"):
        try:
            worktree.validate_slug(bad); assert False, bad
        except ValueError:
            pass
    assert worktree.validate_slug("agent-1") == "agent-1"

    with tempfile.TemporaryDirectory() as d:
        _init_repo(d)

        # two units of work, each its own worktree on its own branch
        a = worktree.create(d, "agent-a")
        b = worktree.create(d, "agent-b")
        assert a.exists() and b.exists() and a != b

        # run them concurrently: each thread binds its own cwd via the contextvar,
        # so a global chdir is never needed and the writes cannot collide
        ts = [threading.Thread(target=_write_in_cwd, args=(a, "config.py", "A")),
              threading.Thread(target=_write_in_cwd, args=(b, "config.py", "B"))]
        for t in ts: t.start()
        for t in ts: t.join()
        assert (a / "config.py").read_text() == "A"        # each worktree kept its own edit
        assert (b / "config.py").read_text() == "B"
        assert (Path(d) / "config.py").read_text() == "shared = 1\n"   # main tree untouched

        # the change gate: a dirty worktree is kept for review, a clean one is removed
        assert worktree.changes(a) > 0
        assert worktree.remove(d, "agent-a") is False      # refused: would lose the edit
        assert a.exists()
        assert worktree.remove(d, "agent-a", force=True) is True   # explicit discard removes it
        assert not a.exists()
        clean = worktree.create(d, "agent-clean")
        assert worktree.changes(clean) == 0
        assert worktree.remove(d, "agent-clean") is True   # nothing written, auto-removed
        assert not clean.exists()

    print("15 worktree isolation: ok")


if __name__ == "__main__":
    test()
