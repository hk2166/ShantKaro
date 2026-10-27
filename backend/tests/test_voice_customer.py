import asyncio

import pytest
from fakes import ScriptedActor, ScriptedJudge
from pipecat.frames.frames import TextFrame, TranscriptionFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.tests.utils import SleepFrame, run_test

from shant.agents.judge import TagEvidence, Verdict
from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.tags import Tag
from shant.voice.customer import Customer
from shant.voice.pipeline import speech_services

SHARMA = load_all()["sharma_uncle"]
SORRY = Verdict(tags=[TagEvidence(tag=Tag.APOLOGISED, quote="sorry")])


def heard(text: str) -> TranscriptionFrame:
    return TranscriptionFrame(text=text, user_id="trainee", timestamp="")


def customer_saying(*replies: str, fail: bool = False) -> Customer:
    verdicts = [SORRY] * len(replies) if replies else [SORRY]
    return Customer(Call(SHARMA, ScriptedActor(list(replies), fail), ScriptedJudge(verdicts), "hi"))


def spoken_by(customer: Customer, monkeypatch: pytest.MonkeyPatch, line: str) -> list[str]:
    spoken: list[str] = []

    async def capture(frame, direction: FrameDirection = FrameDirection.DOWNSTREAM) -> None:
        assert isinstance(frame, TTSSpeakFrame)
        spoken.append(frame.text)

    monkeypatch.setattr(customer, "push_frame", capture)
    asyncio.run(customer.take_turn(line))
    return spoken


def test_the_reply_is_spoken_one_sentence_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying("अरे! तीन हफ्ते हो गए। *sighs* पैसा कब आएगा?")
    spoken = spoken_by(customer, monkeypatch, "sorry sharma ji")
    assert spoken == ["अरे!", "तीन हफ्ते हो गए।", "पैसा कब आएगा?"]
    assert customer.call.state.anger == 65  # the Judge's verdict reached the engine


def test_a_refused_reply_says_nothing_and_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying(fail=True)
    assert spoken_by(customer, monkeypatch, "hello") == []
    assert customer.call.turns == []


def test_a_finished_call_takes_no_more_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying("theek hai")
    customer.call.hang_up()
    assert spoken_by(customer, monkeypatch, "hello") == []


def test_transcripts_become_speech_and_other_frames_pass_through() -> None:
    down, _ = asyncio.run(
        run_test(
            customer_saying("Theek hai."),
            frames_to_send=[heard("  "), TextFrame("caption"), heard("Sorry"), SleepFrame(0.5)],
            expected_down_frames=[TextFrame, TTSSpeakFrame],
        )
    )
    assert isinstance(down[1], TTSSpeakFrame) and down[1].text == "Theek hai."


def test_speech_services_use_the_scenarios_voice_and_languages() -> None:
    stt, tts = speech_services(SHARMA, api_key="test")
    assert stt._settings.language == "en-IN"  # the trainee speaks Hinglish (S1)
    assert (tts._settings.voice, tts._settings.language) == ("Omkar", "hi-IN")
    assert tts._settings.model == "timbre-v2.5"
