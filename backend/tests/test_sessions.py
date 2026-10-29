import asyncio

import pytest
from fakes import ScriptedActor, ScriptedJudge
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.voice.sessions import (
    LIVE_CALLS,
    UnknownScenarioError,
    add_routes,
    live_call,
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
    assert client.get("/health").json() == {"status": "ok", "live_calls": 0}

    async def during_a_call() -> dict:
        async with live_call("s5", new_call(), Stopper().stop, stop_after_s=60):
            return client.get("/health").json()

    assert asyncio.run(during_a_call())["live_calls"] == 1
