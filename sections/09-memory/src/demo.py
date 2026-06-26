"""Section 9 demo: recall a seeded memory into a turn, then extract a new one at
run end, against the Anthropic API. Offline checks live in test.py.

    uv run python sections/09-memory/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import tempfile
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from memory import Store
from permissions import DEFAULT
from tools import Registry

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = "You are a tiny agent. Be brief. Honor any recalled memory."
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
    store = Store(root=root, extractor=lambda messages: [   # run-end extraction writes one new memory
        {"name": "wants-brief", "type": "feedback",
         "description": "User wants brief answers.", "body": "Be terse."}])

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry):
        return client.messages.create(model=MODEL, system=SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    answer = run_turn([{"role": "user", "content": "Given my tabs and spaces preference, how should I indent? One line."}],
                 model, Registry(), Session(mode=DEFAULT), memory=store)
    print("09 memory ->", answer)
    print("09 memory · store now:", sorted(p.name for p in root.glob("*.md")))   # wants-brief.md was added


if __name__ == "__main__":
    demo()
