from datetime import UTC, datetime, timedelta

from shant.voice.limits import (
    CLOSED_FOR_TODAY,
    DAILY_LIMIT,
    IST,
    LINES_BUSY,
    CallCounter,
    Limits,
    client_ip,
)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_limits_come_from_the_environment() -> None:
    env = {
        "SHANT_MAX_LIVE_CALLS": "1",
        "SHANT_CALLS_PER_DAY": "9",
        "SHANT_CALLS_PER_IP_PER_DAY": "2",
    }
    assert Limits.from_env(env) == Limits(max_live_calls=1, calls_per_day=9, calls_per_ip_per_day=2)
    assert Limits.from_env({}) == Limits(
        max_live_calls=3, calls_per_day=150, calls_per_ip_per_day=5
    )


def test_each_limit_refuses_with_its_own_reason() -> None:
    counter = CallCounter(Limits(max_live_calls=2, calls_per_day=3, calls_per_ip_per_day=1))
    assert counter.check("a", live_calls=0) is None
    counter.record("a")
    assert counter.check("a", live_calls=0) == DAILY_LIMIT
    assert counter.check("b", live_calls=2) == LINES_BUSY
    counter.record("b")
    counter.record("c")
    assert counter.check("d", live_calls=0) == CLOSED_FOR_TODAY


def test_the_counts_start_again_at_midnight_in_india() -> None:
    clock = Clock(datetime(2026, 11, 5, 23, 59, tzinfo=IST))
    counter = CallCounter(Limits(calls_per_ip_per_day=1), now=clock)
    counter.record("a")
    assert counter.check("a", live_calls=0) is not None
    clock.now += timedelta(minutes=1)  # 00:00 on Nov 6 in India
    assert counter.check("a", live_calls=0) is None
    assert counter.calls_today == 0


def test_the_day_is_indias_even_when_the_server_runs_on_utc() -> None:
    clock = Clock(datetime(2026, 11, 5, 18, 29, tzinfo=UTC))  # 23:59 in India
    counter = CallCounter(Limits(), now=clock)
    counter.record("a")
    assert counter.calls_today == 1
    clock.now += timedelta(minutes=1)  # 18:30 UTC is midnight in India
    assert counter.calls_today == 0


def test_the_visitor_ip_comes_from_the_proxy_header_when_there_is_one() -> None:
    assert client_ip("203.0.113.7, 10.0.0.1", "10.0.0.1") == "203.0.113.7"
    assert client_ip(None, "198.51.100.2") == "198.51.100.2"
    assert client_ip("", None) == "unknown"
