"""Section 19 demo: the model calls an MCP tool blind.

A knowledge-base server lives in-process here (a real deployment reaches it over
stdio or http; this keeps the run to one file with no extra infra). The demo
discovers its tools with mcp.connect, merges them into the one pool, and runs a
single agent turn. The model never learns who wrote the tool: it just sees
mcp__kb__search in its tool list and calls it, exactly like a built-in.

There is one run_turn in demo(). The agent decides to call the discovered tool;
the harness only supplies the goal and the pool. The tool is read-only, so the
permission gate (section 3) allows it without a prompt.

    uv run python sections/19-mcp-plugins-channels/src/demo.py   (needs ANTHROPIC_API_KEY; see root README)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

import mcp
from loop import Session, run_turn
from permissions import DEFAULT
from tools import Registry

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = ("You answer using only the tools you are given. The knowledge base is an external "
          "MCP server; call its tool to look things up before answering. Be brief, no preamble.")

KB = {
    "worktree": "A git worktree is a second checkout sharing one .git, so parallel work does not collide.",
    "compaction": "Compaction summarizes old turns to keep a long session under the context window.",
}


class KBServer:
    """An in-process MCP server. list_tools is the discovery payload; call runs a
    tool. In production this is a separate process reached over a transport."""

    def list_tools(self):
        return [{"name": "search", "description": "Search the knowledge base by keyword.",
                 "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}},
                                 "required": ["keyword"]},
                 "annotations": {"readOnlyHint": True}}]

    def call(self, tool, args):
        kw = (args.get("keyword") or "").lower()
        return next((v for k, v in KB.items() if k in kw or kw in k), "no entry found")


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("19 mcp: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system, messages=messages,
                                       tools=registry.schemas(), max_tokens=512)

    # Discover the server's tools and merge them into the one pool the loop dispatches.
    reg = Registry()
    for t in mcp.connect("kb", KBServer()):
        reg.register(t)
    print("19 mcp: discovered tools:", [s["name"] for s in reg.schemas()])

    # The one agent call: the model calls the discovered MCP tool blind, then answers.
    answer = run_turn([{"role": "user", "content": "What is a git worktree? Look it up first."}],
                      lambda m, r, s: model(m, r, SYSTEM), reg,
                      Session(mode=DEFAULT, allow_rules=set()))
    print("19 mcp:", answer)


if __name__ == "__main__":
    demo()
