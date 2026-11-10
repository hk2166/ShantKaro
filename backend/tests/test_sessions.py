import asyncio

import pytest
from fakes import ScriptedActor, ScriptedJudge
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.voice import sessions
from shant.voice.limits import CallCounter, Limits
from shant.voice.reports import REPORTS
from shant.voice.sessions import (
    LIVE_CALLS,
    UnknownScenarioError,
    add_routes,
    claim_session,
    live_call,
    report_for,
    scenario_for,
)

SHARMA = load_all()["sharma_uncle"]


def new_call() -> Call:
    return Call(SHARMA, ScriptedActor([]), ScriptedJudge([]), "hi")


def test_the_browser_picks_the_scenario() -> None:
    assert scenario_for({"scenario": "rohan"}, default="sharma_uncle").id == "rohan"


@pytest.mark.parametrize("body", [{}, None, "not a dict", {"scenario": ""}])
def test_without_a_choice_the_default_scenario_plays(body: object) -> None:
    assert scenario_for(body, default="sharma_uncle").id == "sharma_uncle"


def test_an_unknown_scenario_is_refused() -> None:
    with pytest.raises(UnknownScenarioError, match="nobody"):
        scenario_for({"scenario": "nobody"}, default="sharma_uncle")


class Stopper:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


def test_a_call_is_live_only_while_its_pipeline_runs() -> None:
    async def run() -> None:
        async with live_call("s1", new_call(), Stopper().stop, stop_after_s=60):
            assert "s1" in LIVE_CALLS
        assert "s1" not in LIVE_CALLS

    asyncio.run(run())


def test_a_crashed_call_is_not_left_behind() -> None:
    async def run() -> None:
        async with live_call("s2", new_call(), Stopper().stop, stop_after_s=60):
            raise RuntimeError("the pipeline crashed")

    with pytest.raises(RuntimeError):
        asyncio.run(run())
    assert "s2" not in LIVE_CALLS


def test_a_call_that_runs_too_long_is_stopped() -> None:
    stopper = Stopper()

    async def run() -> None:
        async with live_call("s3", new_call(), stopper.stop, stop_after_s=0.01):
            await asyncio.sleep(0.1)  # a hung pipeline

    asyncio.run(run())
    assert stopper.stopped


def test_a_call_that_ends_in_time_is_not_stopped() -> None:
    stopper = Stopper()

    async def run() -> None:
        async with live_call("s4", new_call(), stopper.stop, stop_after_s=0.05):
            pass
        await asyncio.sleep(0.1)  # past the hard stop, but the call already ended

    asyncio.run(run())
    assert not stopper.stopped


def test_health_shows_how_many_calls_are_live() -> None:
    app = FastAPI()
    add_routes(app)
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok", "live_calls": 0, "calls_today": 0}

    async def during_a_call() -> dict:
        async with live_call("s5", new_call(), Stopper().stop, stop_after_s=60):
            return client.get("/health").json()

    assert asyncio.run(during_a_call())["live_calls"] == 1


def test_the_report_starts_while_the_call_is_still_listed_as_live() -> None:
    seen: list[bool] = []

    async def run() -> None:
        async with live_call(
            "s6", new_call(), Stopper().stop, 60, on_end=lambda: seen.append("s6" in LIVE_CALLS)
        ):
            pass

    asyncio.run(run())
    assert seen == [True] and "s6" not in LIVE_CALLS


def test_a_session_starts_only_one_bot() -> None:
    assert claim_session("once")
    assert not claim_session("once")


def test_the_scenario_list_has_what_the_picker_shows() -> None:
    app = FastAPI()
    add_routes(app)
    cards = TestClient(app).get("/scenarios").json()
    assert [card["id"] for card in cards] == ["lakshmi_aunty", "rohan", "sharma_uncle"]
    sharma = cards[2]
    assert sharma["persona"] == {"name": "Sharma Uncle", "age": 58, "city": "Lucknow"}
    assert sharma["languages"] == ["en-IN", "hi-IN"]
    assert sharma["customer_language"] == "hi-IN"
    assert (sharma["company"], sharma["time_limit_s"], sharma["starting_anger"]) == (
        "BharatKart",
        180,
        75,
    )
    assert sharma["allowed_remedies"] and sharma["forbidden_promises"]


def server(limits: Limits) -> TestClient:
    """The routes and limits, with stand-ins for Pipecat's own /start and offer routes."""
    app = FastAPI()
    add_routes(app, CallCounter(limits))

    @app.post("/start")
    async def start() -> dict:
        return {"sessionId": "new"}

    @app.post("/api/offer")
    async def offer() -> dict:
        return {"sdp": "answer"}

    @app.post("/sessions/{session_id}/api/offer")
    async def session_offer(session_id: str) -> dict:
        return {"sdp": "answer"}

    return TestClient(app)


def start(client: TestClient, scenario: str | None = "rohan", ip: str = "1.1.1.1"):
    body = {"transport": "webrtc", "body": {"scenario": scenario} if scenario else {}}
    return client.post("/start", json=body, headers={"x-forwarded-for": ip})


def test_a_visitor_gets_a_few_calls_a_day() -> None:
    client = server(Limits(calls_per_ip_per_day=2))
    assert start(client).json() == {"sessionId": "new"}
    assert start(client).status_code == 200
    refused = start(client)
    assert refused.status_code == 429
    assert refused.json()["error"] == "daily_limit"
    assert start(client, ip="2.2.2.2").status_code == 200  # someone else still can


def test_the_whole_site_closes_when_the_daily_budget_is_spent() -> None:
    client = server(Limits(calls_per_day=2))
    start(client, ip="1.1.1.1")
    start(client, ip="2.2.2.2")
    refused = start(client, ip="3.3.3.3")
    assert refused.status_code == 503
    assert refused.json() == {
        "error": "closed_for_today",
        "message": "Lines are busy, try again tomorrow.",
    }


def test_new_calls_wait_while_all_lines_are_busy() -> None:
    client = server(Limits(max_live_calls=1))

    async def during_a_call():
        async with live_call("busy", new_call(), Stopper().stop, stop_after_s=60):
            return start(client)

    refused = asyncio.run(during_a_call())
    assert refused.status_code == 503 and refused.json()["error"] == "lines_busy"
    assert start(client).status_code == 200  # the line is free again


def test_an_unknown_scenario_is_refused_before_a_call_starts() -> None:
    client = server(Limits())
    refused = start(client, scenario="nobody")
    assert refused.status_code == 400 and refused.json()["error"] == "unknown_scenario"
    assert start(client, scenario=None).status_code == 200  # no choice: the default plays
    assert client.get("/health").json()["calls_today"] == 1  # refusals don't count


def test_bots_start_only_through_a_session() -> None:
    client = server(Limits())
    direct = client.post("/api/offer", json={})
    assert direct.status_code == 403 and direct.json()["error"] == "use_start"
    assert client.post("/sessions/abc/api/offer", json={}).status_code == 200


def test_an_unknown_report_is_not_found() -> None:
    app = FastAPI()
    add_routes(app)
    response = TestClient(app).get("/reports/never-was")
    assert response.status_code == 404 and response.json() == {"error": "not_found"}


def test_a_report_still_being_written_says_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sessions, "REPORT_WAIT_S", 0.05)
    app = FastAPI()
    add_routes(app)
    client = TestClient(app)

    async def during_a_call():
        async with live_call("talking", new_call(), Stopper().stop, stop_after_s=60):
            return client.get("/reports/talking")

    response = asyncio.run(during_a_call())
    assert response.status_code == 202 and response.json() == {"status": "pending"}


def test_waiting_for_a_report_returns_it_once_written() -> None:
    async def run() -> dict | None:
        async def write() -> dict:
            await asyncio.sleep(0.05)
            return {"total": 80}

        REPORTS["written"] = asyncio.create_task(write())
        return await report_for("written", wait_s=1)

    assert asyncio.run(run()) == {"total": 80}


def test_only_the_listed_web_app_may_call_from_another_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHANT_ALLOWED_ORIGINS", "https://shant-karo.vercel.app/, http://x.test")
    app = FastAPI()
    add_routes(app)
    client = TestClient(app)
    allowed = client.get("/health", headers={"Origin": "https://shant-karo.vercel.app"})
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://shant-karo.vercel.app"
    assert "access-control-allow-origin" not in other.headers


def test_without_allowed_origins_no_cross_site_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHANT_ALLOWED_ORIGINS", raising=False)
    app = FastAPI()
    add_routes(app)
    response = TestClient(app).get("/health", headers={"Origin": "https://shant-karo.vercel.app"})
    assert "access-control-allow-origin" not in response.headers
