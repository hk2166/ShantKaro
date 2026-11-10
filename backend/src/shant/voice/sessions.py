"""One bot per call: which scenario it plays, which calls are live, and the hard stop.

The browser starts a call with Pipecat's `POST /start` route, sending the scenario in the
body: `{"body": {"scenario": "rohan"}}`. Pipecat then starts one bot for that session when
the WebRTC connection arrives, and passes the body on to it.

This module also adds the web app's routes: the scenario list, the report card after a call,
the health check, and the cost limits on `/start`.
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.scenarios.schema import Scenario
from shant.voice.limits import CallCounter, Limits, client_ip
from shant.voice.reports import REPORTS

# Calls whose pipeline is still running, by session id. Empty once every call has ended.
LIVE_CALLS: dict[str, Call] = {}
# Sessions that already started a bot. Pipecat would start another bot for every WebRTC offer
# sent to the same session, so a second one is refused.
STARTED_SESSIONS: set[str] = set()
REPORT_WAIT_S = 30.0


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


def claim_session(session_id: str) -> bool:
    """True the first time a session starts a bot, False for any later attempt."""
    if session_id in STARTED_SESSIONS:
        return False
    STARTED_SESSIONS.add(session_id)
    return True


def scenario_card(scenario: Scenario) -> dict:
    """What the scenario picker and the call screen show about one customer."""
    return {
        "id": scenario.id,
        "title": scenario.title,
        "company": scenario.company.name,
        "industry": scenario.company.industry,
        "persona": {
            "name": scenario.persona.name,
            "age": scenario.persona.age,
            "city": scenario.persona.city,
        },
        "summary": scenario.grievance.summary,
        "languages": scenario.trainee_languages,
        "customer_language": scenario.voice.tts_language,
        "allowed_remedies": scenario.policy.allowed_remedies,
        "forbidden_promises": scenario.policy.forbidden_promises,
        "time_limit_s": scenario.dynamics.time_limit_s,
        "starting_anger": scenario.dynamics.starting_anger,
        "max_strikes": scenario.dynamics.max_strikes,
    }


@asynccontextmanager
async def live_call(
    session_id: str,
    call: Call,
    stop: Callable[[], Awaitable[None]],
    stop_after_s: float,
    on_end: Callable[[], None] = lambda: None,
) -> AsyncIterator[None]:
    """Track the call while its pipeline runs, and stop it if it runs past `stop_after_s`.

    The customer already ends the call at its time limit. This is the safety net for when
    something hangs, such as an LLM request that never returns, so no bot is left running.
    `on_end` runs while the call is still listed as live, so the report it starts is never
    missed by someone waiting for it.
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
        try:
            on_end()
        finally:
            del LIVE_CALLS[session_id]


async def report_for(session_id: str, wait_s: float) -> dict | None:
    """The finished report, `{"status": "pending"}` if not ready within `wait_s`, or None."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_s
    while session_id in LIVE_CALLS and session_id not in REPORTS:
        if loop.time() >= deadline:
            return {"status": "pending"}
        await asyncio.sleep(0.25)
    task = REPORTS.get(session_id)
    if task is None:
        return None
    if task.done():
        return task.result()
    done, _ = await asyncio.wait({task}, timeout=max(0.0, deadline - loop.time()))
    return task.result() if done else {"status": "pending"}


def refuse(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse({"error": error, "message": message}, status_code=status)


def add_routes(app: FastAPI, counter: CallCounter | None = None) -> None:
    """Add the web app's routes and the cost limits to Pipecat's server."""
    counter = counter or CallCounter(Limits.from_env())
    scenario_ids = set(load_all())

    @app.get("/health")
    async def health() -> dict:
        """For the host's health check, and to see that no call is left running."""
        return {"status": "ok", "live_calls": len(LIVE_CALLS), "calls_today": counter.calls_today}

    @app.get("/scenarios")
    async def scenarios() -> list[dict]:
        return [scenario_card(scenario) for _, scenario in sorted(load_all().items())]

    @app.get("/reports/{session_id}")
    async def report(session_id: str) -> Response:
        card = await report_for(session_id, REPORT_WAIT_S)
        if card is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(card, status_code=202 if card.get("status") == "pending" else 200)

    @app.middleware("http")
    async def limit_new_calls(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "POST":
            return await call_next(request)
        if request.url.path == "/api/offer":
            # A direct offer would start a bot without going through /start and its limits.
            return refuse(403, "use_start", "Start a call with POST /start.")
        if request.url.path != "/start":
            return await call_next(request)
        try:
            body = (json.loads(await request.body() or b"{}") or {}).get("body") or {}
        except (ValueError, AttributeError):
            body = {}
        requested = body.get("scenario") if isinstance(body, dict) else None
        if requested and requested not in scenario_ids:
            return refuse(400, "unknown_scenario", f"There's no customer called {requested!r}.")
        ip = client_ip(
            request.headers.get("x-forwarded-for"), getattr(request.client, "host", None)
        )
        if refusal := counter.check(ip, live_calls=len(LIVE_CALLS)):
            logger.info(f"call refused for {ip}: {refusal.error}")
            return refuse(*refusal)
        response = await call_next(request)
        if response.status_code == 200:
            counter.record(ip)
        return response

    # The web app may be hosted elsewhere (Vercel). Added last, so it wraps the limits above
    # and refusals reach the browser with CORS headers too.
    if origins := allowed_origins():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["*"],
        )


def allowed_origins(env: dict[str, str] | None = None) -> list[str]:
    """Sites allowed to call this server, from SHANT_ALLOWED_ORIGINS (comma-separated)."""
    value = (env if env is not None else os.environ).get("SHANT_ALLOWED_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


def use_stun_servers(env: dict[str, str] | None = None) -> list[str]:
    """Give Pipecat's WebRTC handler STUN servers from SHANT_STUN_SERVERS (comma-separated).

    A cloud server (AWS EC2) sees only its private address, so without STUN it offers callers an
    address they can't reach. Pipecat's runner builds its WebRTC handler with no ICE servers and
    no option to set them, so this wraps the handler's constructor. Call it before `main()`.
    """
    value = (env if env is not None else os.environ).get("SHANT_STUN_SERVERS", "")
    servers = [url.strip() for url in value.split(",") if url.strip()]
    if not servers:
        return []
    from pipecat.transports.smallwebrtc.connection import IceServer
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler

    original = SmallWebRTCRequestHandler.__init__
    stun = [IceServer(urls=url) for url in servers]

    def init_with_stun(self, *args: Any, ice_servers: Any = None, **kwargs: Any) -> None:
        original(self, *args, ice_servers=ice_servers or stun, **kwargs)

    SmallWebRTCRequestHandler.__init__ = init_with_stun  # type: ignore[method-assign]
    return servers
