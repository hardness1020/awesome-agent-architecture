"""Section 14 demo: a scheduled prompt fires on the clock and drives a real
turn, with no human pressing enter. Offline checks live in test.py.

We schedule a one-shot prompt a second into the future and start the tick
thread. When the clock catches up, the scheduler enqueues the prompt (it never
calls the model itself); the driver drains it between turns and runs it as a new
user-style turn (section 1). That is the whole point of scheduling: the loop
fires itself.

    uv run python sections/14-scheduling/src/demo.py    (needs ANTHROPIC_API_KEY; see root README)
"""
import os
import subprocess
import time

from anthropic import Anthropic
from dotenv import load_dotenv

from loop import Session, run_turn
from permissions import DEFAULT
from scheduler import Scheduler, deliver
from tools import Registry, Tool

load_dotenv(override=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SYSTEM = "You are a tiny scheduled agent. Use the shell when asked, then answer in one line."


def demo():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("14 scheduling: set ANTHROPIC_API_KEY to run the live demo (offline checks: test.py)")
        return

    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)

    def model(messages, registry, system):
        return client.messages.create(model=MODEL, system=system or SYSTEM, messages=messages,
                                       tools=registry.schemas(), max_tokens=512)

    def sh(a):
        return subprocess.run(a["command"], shell=True, capture_output=True, text=True, timeout=60).stdout.strip()

    reg = Registry()
    reg.register(Tool("Bash", sh, description="Run a shell command.",
                      input_schema={"type": "object", "properties": {"command": {"type": "string"}},
                                    "required": ["command"]}))
    session = Session(mode=DEFAULT, allow_rules={"Bash"})

    channels = {"console": lambda text: print("14 scheduling · [console] <-", text)}
    sched = Scheduler()                                    # local clock, no durability for the demo
    sched.run()                                            # start the 1s tick thread
    sched.create("Count the files in the current directory with the shell, then report the "
                 "number. If somehow there are zero files, start your reply with [SILENT].",
                 due=time.time() + 1, channel="console")   # fires ~1s from now, no human input
    print("14 scheduling: scheduled a one-shot, waiting for the clock to fire it...")

    fired = []
    for _ in range(20):                                    # let the tick thread catch up
        fired = sched.drain()
        if fired:
            break
        time.sleep(0.5)
    sched.stop()

    if not fired:
        print("14 scheduling: nothing fired (clock never advanced?)")
        return

    for task in fired:                                     # the driver: each fired task is a new turn
        messages = [{"role": "user", "content": task["prompt"]}]
        answer = run_turn(messages, model, reg, session)
        if not deliver(channels, task, answer):            # no human asked, so the answer must route out
            print("14 scheduling -> fired turn (undelivered):", answer)


if __name__ == "__main__":
    demo()
