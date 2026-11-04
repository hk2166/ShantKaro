"""Cost limits: how many calls may run at once, per day, and per visitor per day.

Every call spends LLM and Gnani credits, so a public demo needs caps. A call lasts at most
3 minutes (plus the hard stop), so counting calls bounds the credits spent. The limits are
checked when the browser asks Pipecat's `POST /start` for a new call.
"""

import os
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Limits:
    max_live_calls: int = 3
    calls_per_day: int = 150
    calls_per_ip_per_day: int = 5

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Limits":
        defaults = cls()
        return cls(
            max_live_calls=int(env.get("SHANT_MAX_LIVE_CALLS", defaults.max_live_calls)),
            calls_per_day=int(env.get("SHANT_CALLS_PER_DAY", defaults.calls_per_day)),
            calls_per_ip_per_day=int(
                env.get("SHANT_CALLS_PER_IP_PER_DAY", defaults.calls_per_ip_per_day)
            ),
        )


class Refusal(NamedTuple):
    """Why a new call can't start: the HTTP status, a code for the app, and words for people."""

    status: int
    error: str
    message: str


LINES_BUSY = Refusal(503, "lines_busy", "All our lines are busy. Try again in a minute.")
CLOSED_FOR_TODAY = Refusal(503, "closed_for_today", "Lines are busy, try again tomorrow.")
DAILY_LIMIT = Refusal(429, "daily_limit", "You've used today's free calls. Come back tomorrow!")


def ist_now() -> datetime:
    return datetime.now(IST)


class CallCounter:
    """Counts the calls started today (IST), in total and per client IP."""

    def __init__(self, limits: Limits, now: Callable[[], datetime] = ist_now) -> None:
        self.limits = limits
        self._now = now
        self._day: date = now().astimezone(IST).date()
        self._per_ip: Counter[str] = Counter()

    def _roll_over(self) -> None:
        today = self._now().astimezone(IST).date()
        if today != self._day:
            self._day, self._per_ip = today, Counter()

    @property
    def calls_today(self) -> int:
        self._roll_over()
        return self._per_ip.total()

    def check(self, ip: str, live_calls: int) -> Refusal | None:
        """The reason this IP can't start a call now, or None if it can."""
        self._roll_over()
        if live_calls >= self.limits.max_live_calls:
            return LINES_BUSY
        if self._per_ip.total() >= self.limits.calls_per_day:
            return CLOSED_FOR_TODAY
        if self._per_ip[ip] >= self.limits.calls_per_ip_per_day:
            return DAILY_LIMIT
        return None

    def record(self, ip: str) -> None:
        self._roll_over()
        self._per_ip[ip] += 1


def client_ip(forwarded_for: str | None, peer: str | None) -> str:
    """The visitor's IP: the first `X-Forwarded-For` entry, else the connecting address.

    Only trust this behind a proxy that sets `X-Forwarded-For` itself. Without one, a visitor
    can send any value in that header and dodge the per-IP limit (the other limits still hold).
    """
    if forwarded_for and (first := forwarded_for.split(",")[0].strip()):
        return first
    return peer or "unknown"
