"""Section 9 demo: recall a seeded memory into a turn, search a past session's
raw history with a tool, then extract a new memory at run end, against the
Anthropic API. Offline checks live in test.py.

    uv run python sections/09-memory/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import tempfile
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from memory import Store, log_run, search_tool
from permissions import DEFAULT
from tools import Registry

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = ("You are a tiny agent. Be brief. Honor any recalled memory. "
          "Use SessionSearch when the answer may live in a past session.")
SEEDS = [   # the durable store; Claude Code keeps these under ~/.claude/projects/<root>/memory
    ("style-tabs", "feedback", "User prefers tabs not spaces for indentation.", "Indent with tabs."),
    ("deploy-fri", "project", "Never deploy on Fridays.", "Releases wait for Monday."),
]


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("09 memory: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    root = Path(tempfile.mkdtemp())                       # a disposable store, seeded below
    for name, type_, desc, body in SEEDS:
        (root / f"{name}.md").write_text(f"---\ntype: {type_}\ndescription: {desc}\n---\n{body}\n")

    db = root / "state.db"                                # a past session no memory was extracted from
    log_run(db, "last-week", [{"role": "user",
                               "content": "note: the staging database password rotates every Tuesday"}])
    store = Store(root=root, db=db, session_id="today",   # this run logs itself the same way
                  extractor=lambda messages: [            # run-end extraction writes one new memory
        {"name": "wants-brief", "type": "feedback",
         "description": "User wants brief answers.", "body": "Be terse."}])

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    reg = Registry()
    reg.register(search_tool(db))                         # raw-history recall is the model's call

    answer = run_turn([{"role": "user", "content":
                        "When does the staging database password rotate? One line."}],
                 model, reg, Session(mode=DEFAULT), memory=store)
    print("09 memory ->", answer)
    print("09 memory · store now:", sorted(p.name for p in root.glob("*.md")))   # wants-brief.md was added


if __name__ == "__main__":
    demo()
