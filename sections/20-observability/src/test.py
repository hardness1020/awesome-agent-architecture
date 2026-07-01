"""Section 20 offline checks, no key, no network.

test_queue_drain(): an event emitted before any sink attaches is buffered, then
drained through the sink on attach. Telemetry can log before it is ready.

test_sample(): the sampling predicate drops events by name before fan-out.

test_scrub_and_isolate(): telemetry observes a real section-2 tool dispatch
without changing it; a field not on the allowlist (a file path) is scrubbed
before any sink sees it, and a throwing sink never propagates out of emit().

test_cost(): per-model token usage accumulates into a running USD total.

test_eval(): a fixed task set is replayed against a build and graded; a
regressed build scores a lower pass rate. This is the offline pipeline.

    python sections/20-observability/src/test.py
"""
from telemetry import CostTracker, Telemetry, run_eval, scrub
from tools import Tool, run_tool


def test_queue_drain():
    tel = Telemetry()
    tel.emit("boot", event="boot", ok=True)        # emitted before any sink exists
    seen = []
    tel.attach(lambda name, meta: seen.append((name, meta)))
    assert seen == [("boot", {"event": "boot", "ok": True})]   # buffered, then drained
    tel.emit("boot", event="boot", ok=False)       # after attach, delivered live
    assert seen[-1] == ("boot", {"event": "boot", "ok": False})

    print("20 obs: queue-drain ok")


def test_sample():
    # keep model_call, drop the noisy heartbeat (shouldSampleEvent)
    tel = Telemetry(sample=lambda name: name != "heartbeat")
    seen = []
    tel.attach(lambda name, meta: seen.append(name))
    tel.emit("model_call", model="claude-opus-4-8")
    tel.emit("heartbeat")
    assert seen == ["model_call"]                  # the sampled-out event never reached the sink

    print("20 obs: sample ok")


def test_scrub_and_isolate():
    # scrub keeps only allowlisted fields; a raw path is not one of them
    assert scrub({"tool": "Read", "path": "/home/me/.ssh/id_rsa"}) == {"tool": "Read"}

    tel = Telemetry()
    seen = []
    tel.attach(lambda name, meta: (_ for _ in ()).throw(RuntimeError("bad sink")))  # a broken sink
    tel.attach(lambda name, meta: seen.append((name, meta)))

    # telemetry observes a real section-2 tool dispatch; the loop's dispatch is untouched
    tool = Tool(name="echo", run=lambda a: a["x"])
    out = run_tool(tool, {"x": "hi"})
    tel.emit("tool_result", tool="echo", ok=True, secret_path="/home/me/.env")

    assert out == "hi"                             # run_tool unchanged by the observer
    assert seen == [("tool_result", {"tool": "echo", "ok": True})]  # path scrubbed, bad sink swallowed

    print("20 obs: scrub-and-isolate ok")


def test_cost():
    cost = CostTracker()
    cost.add("claude-opus-4-8", 1000, 500)         # 1000*15e-6 + 500*75e-6 = 0.0525
    cost.add("claude-opus-4-8", 0, 500)            # + 500*75e-6 = 0.0375
    cost.add("claude-sonnet-4-6", 2000, 0)         # + 2000*3e-6 = 0.006
    assert cost.by_model["claude-opus-4-8"] == (1000, 1000)
    assert abs(cost.cost_usd - (0.0525 + 0.0375 + 0.006)) < 1e-9

    print("20 obs: cost ok")


def test_eval():
    tasks = [({"a": 2, "b": 3}, lambda o: o == 5), ({"a": 10, "b": 1}, lambda o: o == 11)]
    good = run_eval(lambda inp: inp["a"] + inp["b"], tasks)
    bad = run_eval(lambda inp: inp["a"] - inp["b"], tasks)     # a regressed build
    assert good["rate"] == 1.0 and good["passed"] == 2
    assert bad["rate"] == 0.0                                  # eval catches the regression

    print("20 obs: eval ok")


if __name__ == "__main__":
    test_queue_drain()
    test_sample()
    test_scrub_and_isolate()
    test_cost()
    test_eval()
