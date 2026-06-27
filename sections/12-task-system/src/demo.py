"""Section 12 demo: the model planning real work into durable tasks on disk,
against the Anthropic API. Offline checks live in test.py.

The model gets TaskCreate / TaskUpdate / TaskGet / TaskList and is asked to lay
out a small dependency graph. The tasks outlive the turn as JSON files.

    uv run python sections/12-task-system/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import tempfile

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from tasks import TaskStore, task_tools
from tools import Registry

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = "You are a tiny agent. Plan work with the Task tools, then list the tasks. Be brief."


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("12 tasks: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system or SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    with tempfile.TemporaryDirectory() as d:
        reg = Registry()
        for t in task_tools(TaskStore(d)):
            reg.register(t)

        # TaskCreate / TaskUpdate are writes; allow-list them so the gate (section 3) doesn't ask
        session = Session(mode=DEFAULT, allow_rules={"TaskCreate", "TaskUpdate"})
        answer = run_turn(
            [{"role": "user", "content": "Plan a feature: schema, then API (blocked by schema), then tests "
                                         "(blocked by API). Create the tasks with the right dependencies, then list them."}],
            model, reg, session)
        print("12 tasks ->", answer)
        print("12 tasks: on-disk files ->", sorted(p.name for p in os.scandir(d)))


if __name__ == "__main__":
    demo()
