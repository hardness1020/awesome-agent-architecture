"""Evaluation (section 23): the environment a score comes from.

Section 20's run_eval takes (input, grade) pairs: one string in, one string
out, one pass rate. An agent that asks the user a question and then changes
stored data cannot be graded that way. This module builds the test bed it
needs, the five elements of an evaluation environment:

  dataset   the task records passed to run_suite
  state     Env.state, the mutable data a task starts from and ends in
  tools     Env.tools, the operations the agent is allowed to run
  rubric    the checks, communication strings, and vetoes in grade()
  protocol  run_episode, which alternates user turn and agent turn

reset() puts the state back before every episode, so no run inherits the last
run's writes. The simulated user releases one fact per turn, so the agent has
to ask instead of reading the whole task off the first message.

grade() reads the final state (the outcome), not the transcript, plus process
metrics (illegal calls, steps) and a zero-tolerance veto. Repeats split one
verdict into Pass@k (can it) and Pass^k (does it every time), and the binomial
standard error gives the band under which a gap between two builds is noise.

Mirrors the five elements and the metric dictionary from the book chapter 6,
plus tau-bench's simulated user and end-state comparison: any trajectory that
reaches the target state passes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from math import sqrt


@dataclass
class Env:
    """A resettable test bed: state plus the tools that change it."""
    initial: dict                                     # the snapshot every episode starts from
    tools: dict                                       # name -> fn(state, **args) -> str
    state: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)         # (name, legal) per call, for process metrics

    def reset(self) -> None:
        """Put the state back. A deep copy, so one episode never sees the last one's writes."""
        self.state = deepcopy(self.initial)
        self.calls = []

    def call(self, name: str, **args) -> str:
        """Run one tool against the state. A rejected call is a message, not a crash."""
        tool = self.tools.get(name)
        if tool is None:
            self.calls.append((name, False))          # illegal: a tool that does not exist
            return f"error: no tool named {name}"
        try:
            out = tool(self.state, **args)
        except Exception as e:                        # illegal: wrong arguments. Say why, then continue
            self.calls.append((name, False))
            return f"error: {type(e).__name__}: {e}"
        self.calls.append((name, True))
        return str(out)


def scripted_user(facts):
    """A simulated user that releases one fact per turn (progressive disclosure).

    facts[0] opens the conversation; each later fact is released only when the
    agent replies again. The live version is an LLM given the same script, so
    the wording varies while the order of disclosure does not."""
    def start():
        pending = list(facts)
        return lambda _agent_text=None: pending.pop(0) if pending else None   # None ends the episode
    return start


def run_episode(env: Env, task: dict, agent, max_turns: int = 8) -> dict:
    """The interaction protocol: reset, then alternate user turn and agent turn.

    agent(said, env) -> reply text; it reaches the state only through env.call.
    Returns the transcript, the final state, and the call log."""
    env.reset()
    user = task["user"]()                             # a fresh simulated user per episode
    transcript = []
    said = user()
    for _ in range(max_turns):                        # the ceiling: an episode always terminates
        if said is None:
            break
        reply = agent(said, env)
        transcript.append((said, reply))
        said = user(reply)
    return {"transcript": transcript, "state": env.state, "calls": list(env.calls)}


def grade(task: dict, run: dict) -> dict:
    """Score one episode: outcome first, then what was said, then the veto.

    checks read the final state, so any path that reaches it passes. must_say
    catches "claimed but never did" in reverse: work done, user never told.
    A veto is zero tolerance: one hit fails the run whatever else scored."""
    checks = {name: bool(fn(run["state"])) for name, fn in task["checks"]}
    said = " ".join(reply for _, reply in run["transcript"]).lower()
    told = {s: s.lower() in said for s in task.get("must_say", [])}
    unsafe = [name for name, fn in task.get("veto", []) if fn(run)]
    return {"passed": all(checks.values()) and all(told.values()) and not unsafe,
            "checks": checks, "told": told, "unsafe": unsafe,
            "illegal_calls": sum(1 for _, ok in run["calls"] if not ok),
            "steps": len(run["calls"])}


def score(task: dict, agent, k: int = 1) -> dict:
    """Run one task k times. Pass@k asks can it, Pass^k asks does it every time."""
    runs = [grade(task, run_episode(task["env"](), task, agent)) for _ in range(k)]
    ok = [r["passed"] for r in runs]
    return {"task": task["id"], "pass_at_k": any(ok), "pass_hat_k": all(ok), "runs": runs}


def run_suite(agent, tasks, k: int = 1) -> dict:
    """Section 20's run_eval, now with an environment, a reset, and a protocol.

    rate is the Pass^k rate: a task counts only if every one of its k runs
    passed. band is the noise under which a difference is not a result."""
    per_task = [score(t, agent, k) for t in tasks]
    n = len(per_task) or 1
    rate = sum(t["pass_hat_k"] for t in per_task) / n
    return {"tasks": len(per_task), "k": k, "rate": rate,
            "pass_at_k": sum(t["pass_at_k"] for t in per_task) / n,
            "band": noise_band(rate, n), "per_task": per_task}


def noise_band(rate: float, n: int) -> float:
    """Binomial standard error: the sampling noise on a pass rate over n tasks.

    A gap of one band between two builds is not a result. Two builds run on the
    same tasks should be compared with paired(), which is the sharper test."""
    return sqrt(rate * (1 - rate) / n) if n else 0.0


def paired(before: dict, after: dict) -> dict:
    """Compare two suite results task by task. Only the tasks that changed carry information."""
    b = {t["task"]: t["pass_hat_k"] for t in before["per_task"]}
    a = {t["task"]: t["pass_hat_k"] for t in after["per_task"]}
    return {"fixed": [k for k in b if not b[k] and a.get(k)],
            "broke": [k for k in b if b[k] and not a.get(k)]}
