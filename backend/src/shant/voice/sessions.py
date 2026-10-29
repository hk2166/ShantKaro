"""One bot per call: which scenario it plays, which calls are live, and the hard stop.

The browser starts a call with Pipecat's `POST /start` route, sending the scenario in the
body: `{"body": {"scenario": "rohan"}}`. Pipecat then starts one bot for that session when
the WebRTC connection arrives, and passes the body on to it.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from loguru import logger

from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.scenarios.schema import Scenario

# Calls whose pipeline is still running, by session id. Empty once every call has ended.
LIVE_CALLS: dict[str, Call] = {}


class UnknownScenarioError(ValueError):
    pass


def scenario_for(body: Any, default: str) -> Scenario:
    """The scenario the browser asked for, or `default` when it didn't say."""
    scenarios = load_all()
    requested = body.get("scenario") if isinstance(body, dict) else None
    scenario_id = requested or default
    if scenario_id not in scenarios:
        raise UnknownScenarioError(f"no scenario called {scenario_id!r}")
    return scenarios[scenario_id]


@asynccontextmanager
async def live_call(
    session_id: str, call: Call, stop: Callable[[], Awaitable[None]], stop_after_s: float
) -> AsyncIterator[None]:
    """Track the call while its pipeline runs, and stop it if it runs past `stop_after_s`.

    The customer already ends the call at its time limit. This is the safety net for when
    something hangs, such as an LLM request that never returns, so no bot is left running.
    """

    async def hard_stop() -> None:
        await asyncio.sleep(stop_after_s)
        logger.warning(f"hard stop: call {session_id} ran past {stop_after_s:.0f} s")
        await stop()

    LIVE_CALLS[session_id] = call
    watchdog = asyncio.create_task(hard_stop())
    try:
        yield
    finally:
        watchdog.cancel()
        del LIVE_CALLS[session_id]


def add_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict:
        """For the host's health check, and to see that no call is left running."""
        return {"status": "ok", "live_calls": len(LIVE_CALLS)}
