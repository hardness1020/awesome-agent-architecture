"""Section 13 demo: a whole subagent runs in the background while the main loop
keeps going, against the Anthropic API. Offline checks live in test.py.

Turn 1: the model launches a whole agent (section 6) with run_in_background and
gets a handle immediately, the main loop never blocks. Turn 2: the completed
<task_notification> is drained into the next user message, so the model reports
what the background subagent found.

    uv run python sections/13-background-execution/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import subprocess
import time

from anthropic import Anthropic
from dotenv import load_dotenv

from background import Runtime, backgroundable
from loop import Session, run_turn
from permissions import DEFAULT
from subagents import agent_tool
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = "You are a tiny agent. Delegate slow work to a background subagent with run_in_background. Be brief."


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("13 background: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system or SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=1024)

    runtime = Runtime()
    session = Session(mode=DEFAULT, allow_rules={"Bash"})

    def sh(a):                                             # a plain shell tool for the child
        return subprocess.run(a["command"], shell=True, capture_output=True, text=True, timeout=120).stdout.strip()

    bash = Tool("Bash", sh, description="Run a shell command.",
                input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                              "required": ["command"]})

    # the child subagent's own toolset: it runs shell inline, and has no Agent tool, so it can't recurse
    child = Registry()
    child.register(bash)

    reg = Registry()
    # backgroundable wraps the WHOLE agent: one call runs a full sub-loop off the main loop
    reg.register(backgroundable(agent_tool(model, child, session), runtime))

    messages = [{"role": "user", "content": "Launch a background subagent to count the files in /etc with shell. "
                                            "Just tell me you started it, do not wait for it."}]
    print("13 background -> turn 1:", run_turn(messages, model, reg, session, runtime=runtime))

    for _ in range(60):                                    # let the whole subagent run its own loop off-loop
        if runtime.state(1) != "running":
            break
        time.sleep(0.5)

    messages.append({"role": "user", "content": "Did the background subagent finish? What did it find?"})
    print("13 background -> turn 2:", run_turn(messages, model, reg, session, runtime=runtime))


if __name__ == "__main__":
    demo()
