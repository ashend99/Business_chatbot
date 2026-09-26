"""SlidingWindowLimiter with a controllable clock."""

import pytest

from app.services import rate_limit
from app.services.rate_limit import SlidingWindowLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_allows_up_to_the_limit_then_reports_retry_after(clock) -> None:
    limiter = SlidingWindowLimiter(3, window_seconds=60, clock=clock)
    assert [limiter.hit("k") for _ in range(3)] == [None, None, None]
    clock.now += 10
    assert limiter.hit("k") == pytest.approx(50)


def test_window_slides(clock) -> None:
    limiter = SlidingWindowLimiter(2, window_seconds=60, clock=clock)
    limiter.hit("k")
    clock.now += 30
    limiter.hit("k")
    clock.now += 31  # the first hit has left the window
    assert limiter.hit("k") is None
    assert limiter.hit("k") is not None


def test_rejected_requests_are_not_counted(clock) -> None:
    limiter = SlidingWindowLimiter(1, window_seconds=60, clock=clock)
    limiter.hit("k")
    for _ in range(5):
        clock.now += 10
        limiter.hit("k")
    clock.now += 11  # 61s after the only counted hit
    assert limiter.hit("k") is None


def test_keys_are_independent(clock) -> None:
    limiter = SlidingWindowLimiter(1, clock=clock)
    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.hit("a") is not None


def test_idle_keys_are_swept(clock, monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "_SWEEP_THRESHOLD", 5)
    limiter = SlidingWindowLimiter(10, window_seconds=60, clock=clock)
    for i in range(6):
        limiter.hit(i)
    clock.now += 120
    limiter.hit("fresh")
    assert set(limiter._hits) == {"fresh"}
