"""Section 11 offline checks: each recovery path with a fake flaky call.
No key, no network.

    python sections/11-error-recovery/src/test.py
"""
import recovery
from recovery import FallbackTriggered, retry_delay, should_retry, with_retry

NOSLEEP = lambda *_: None


class FakeError(Exception):
    def __init__(self, status_code=None, overflow=False, retry_after=None):
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        self.overflow = overflow
        self.retry_after = retry_after


def test():
    # classification and backoff
    assert should_retry(529) and should_retry(429) and not should_retry(400)
    assert retry_delay(1, retry_after=7) == 7.0                   # server header wins
    assert retry_delay(1) <= recovery.BASE_DELAY * 1.25           # base + <=25% jitter
    assert retry_delay(99) <= recovery.MAX_DELAY * 1.25           # capped

    # transient: two 529s, then success
    n = {"i": 0}
    def flaky():
        n["i"] += 1
        if n["i"] < 3:
            raise FakeError(status_code=529)
        return "ok"
    assert with_retry(flaky, sleep=NOSLEEP) == "ok" and n["i"] == 3

    # fatal: a 400 surfaces immediately, no retries
    b = {"i": 0}
    def fatal():
        b["i"] += 1
        raise FakeError(status_code=400)
    try:
        with_retry(fatal, sleep=NOSLEEP)
        assert False
    except FakeError:
        assert b["i"] == 1

    # overflow: on_overflow runs once, then the retry succeeds
    seen = {"compacted": 0, "i": 0}
    def over():
        seen["i"] += 1
        if seen["i"] == 1:
            raise FakeError(overflow=True)
        return "fits now"
    assert with_retry(over, on_overflow=lambda: seen.__setitem__("compacted", 1), sleep=NOSLEEP) == "fits now"
    assert seen["compacted"] == 1

    # overflow that never shrinks: compact once, then surface (no infinite loop)
    def always_over():
        raise FakeError(overflow=True)
    try:
        with_retry(always_over, on_overflow=lambda: None, sleep=NOSLEEP)
        assert False
    except FakeError:
        pass

    # 529 storm: with a fallback, raise FallbackTriggered after MAX_529_RETRIES
    def overload():
        raise FakeError(status_code=529)
    try:
        with_retry(overload, fallback_model="haiku", sleep=NOSLEEP)
        assert False
    except FallbackTriggered as e:
        assert e.fallback_model == "haiku"

    print("11 recovery: ok")


if __name__ == "__main__":
    test()
