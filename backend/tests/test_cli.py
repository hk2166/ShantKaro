import asyncio
from collections.abc import Iterator
from dataclasses import replace

import pytest
from fakes import ScriptedActor, ScriptedJudge

from shant.agents.judge import TagEvidence, Verdict
from shant.cli import brief, meter, outcome, play
from shant.engine.state import Status
from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.tags import Tag

SHARMA = load_all()["sharma_uncle"]


def call_with(**state_changes: object) -> Call:
    call = Call(SHARMA, ScriptedActor([]), ScriptedJudge([]), "hello")
    call.state = replace(call.state, **state_changes)
    return call


def test_meter_shows_anger_clock_and_strikes() -> None:
    line = meter(call_with(anger=50, strikes=1), elapsed_s=75)
    assert "█" * 10 + "░" * 10 in line
    assert "50 · 1:15 / 3:00 · strikes 1/3" in line


def test_brief_lists_what_the_agent_may_and_must_not_offer() -> None:
    text = brief(SHARMA)
    assert all(f"+ {item}" in text for item in SHARMA.policy.allowed_remedies)
    assert all(f"- {item}" in text for item in SHARMA.policy.forbidden_promises)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"status": Status.WON}, "You win"),
        ({"status": Status.TIMED_OUT}, "Time's up"),
        ({"status": Status.ENDED_BY_TRAINEE}, "You ended the call"),
        ({"status": Status.HUNG_UP, "anger": 100}, "lost patience"),
        ({"status": Status.HUNG_UP, "strikes": 3}, "promises the company can't keep"),
    ],
)
def test_outcome_explains_how_the_call_ended(changes: dict, expected: str) -> None:
    assert expected in outcome(call_with(**changes))


def keyboard(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> None:
    typed: Iterator[str] = iter(lines)

    def fake_input(prompt: str = "") -> str:
        try:
            return next(typed)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)


def test_playing_well_wins_the_call(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    keyboard(monkeypatch, ["", "Sharma ji I am really sorry", "ticket bkr4562"])
    calm = Verdict(
        tags=[
            TagEvidence(tag=Tag.APOLOGISED, quote="really sorry"),
            TagEvidence(tag=Tag.USED_NAME, quote="sharma ji"),
        ]
    )
    fixed = Verdict(tags=[TagEvidence(tag=Tag.CONCRETE_NEXT_STEP, quote="ticket bkr4562")])
    big_calm = SHARMA.model_copy(
        update={
            "dynamics": SHARMA.dynamics.model_copy(
                update={"tag_weights": {**SHARMA.dynamics.tag_weights, Tag.APOLOGISED: -50}}
            )
        }
    )
    call = asyncio.run(
        play(big_calm, 15, ScriptedActor(["theek hai", "achha"]), ScriptedJudge([calm, fixed]))
    )
    assert call.state.status is Status.WON
    assert call.turns[0].agent == "sharma ji i am really sorry"
    assert "You win" in capsys.readouterr().out


def test_quit_and_end_of_input_both_hang_up(monkeypatch: pytest.MonkeyPatch) -> None:
    keyboard(monkeypatch, ["/quit"])
    assert asyncio.run(play(SHARMA, 15, ScriptedActor([]), ScriptedJudge([]))).state.status is (
        Status.ENDED_BY_TRAINEE
    )
    keyboard(monkeypatch, [])
    assert asyncio.run(play(SHARMA, 15, ScriptedActor([]), ScriptedJudge([]))).state.status is (
        Status.ENDED_BY_TRAINEE
    )


def test_a_refused_reply_lets_the_trainee_try_again(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    keyboard(monkeypatch, ["hello"])
    call = asyncio.run(play(SHARMA, 15, ScriptedActor([], fail=True), ScriptedJudge([])))
    assert "went quiet" in capsys.readouterr().out
    assert call.turns == []
