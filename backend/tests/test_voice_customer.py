import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from fakes import ScriptedActor, ScriptedJudge
from pipecat.frames.frames import (
    EndWorkerFrame,
    Frame,
    InterruptionFrame,
    STTUpdateSettingsFrame,
    TextFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import (
    RTVIClientMessageFrame,
    RTVIServerMessageFrame,
    RTVIServerResponseFrame,
)
from pipecat.services.settings import STTSettings
from pipecat.tests.utils import SleepFrame, run_test

from shant.agents.judge import TagEvidence, Verdict
from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.tags import Tag
from shant.voice.customer import Customer
from shant.voice.gnani_tts import PacedGnaniTTS
from shant.voice.pipeline import barge_in, speech_services

SHARMA = load_all()["sharma_uncle"]
ENDINGS = SHARMA.closing_lines


def verdict(*pairs: tuple[Tag, str]) -> Verdict:
    """The Judge's tags, each with the quote it points at in the trainee's line."""
    return Verdict(tags=[TagEvidence(tag=tag, quote=quote) for tag, quote in pairs])


SORRY = verdict((Tag.APOLOGISED, "sorry"))


def heard(text: str) -> TranscriptionFrame:
    return TranscriptionFrame(text=text, user_id="trainee", timestamp="")


def customer_saying(
    *replies: str,
    verdicts: list[Verdict] | None = None,
    fail: bool = False,
    speeds: list[float] | None = None,
) -> Customer:
    judged = verdicts or [SORRY] * max(len(replies), 1)
    call = Call(SHARMA, ScriptedActor(list(replies), fail), ScriptedJudge(judged), "hi")
    return Customer(call, set_speed=speeds.append if speeds is not None else lambda _: None)


def capture(customer: Customer, monkeypatch: pytest.MonkeyPatch) -> list[Frame]:
    """Collect every frame the customer pushes, instead of sending it down a pipeline."""
    pushed: list[Frame] = []

    async def push(frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM) -> None:
        pushed.append(frame)

    monkeypatch.setattr(customer, "push_frame", push)
    return pushed


def spoken(frames: list[Frame]) -> list[str]:
    return [frame.text for frame in frames if isinstance(frame, TTSSpeakFrame)]


def states(frames: list[Frame]) -> list[dict]:
    return [frame.data for frame in frames if isinstance(frame, RTVIServerMessageFrame)]


def test_the_reply_is_spoken_one_sentence_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying("अरे! तीन हफ्ते हो गए। *sighs* पैसा कब आएगा?")
    pushed = capture(customer, monkeypatch)
    asyncio.run(customer.take_turn("sorry sharma ji"))
    assert spoken(pushed) == ["अरे!", "तीन हफ्ते हो गए।", "पैसा कब आएगा?"]
    assert customer.call.state.anger == 65  # the Judge's verdict reached the engine


def test_the_browser_gets_the_new_state_after_each_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying("Hmm.")
    pushed = capture(customer, monkeypatch)
    asyncio.run(customer.take_turn("sorry"))
    [state] = states(pushed)
    assert state["type"] == "call_state"
    assert (state["anger"], state["status"], state["last_tags"]) == (
        65,
        "in_progress",
        ["apologised"],
    )
    assert isinstance(pushed[-1], RTVIServerMessageFrame)  # sent after the reply, not before


def test_the_voice_speeds_up_and_slows_down_with_anger(monkeypatch: pytest.MonkeyPatch) -> None:
    speeds: list[float] = []
    calming = verdict((Tag.APOLOGISED, "sorry"), (Tag.ACKNOWLEDGED_FEELING, "i understand"))
    dismissive = verdict((Tag.DISMISSIVE, "relax uncle"))
    customer = customer_saying("Hmm.", "Kya?", verdicts=[calming, dismissive], speeds=speeds)
    assert speeds == [1.08]  # Sharma starts at 75, in the "angry" band
    capture(customer, monkeypatch)
    asyncio.run(customer.take_turn("i'm so sorry, i understand"))
    assert speeds[-1] == 1.0  # 75 − 18 = 57: "irritated"
    asyncio.run(customer.take_turn("relax uncle"))
    assert speeds[-1] == 1.08  # 57 + 15 = 72: angry again


def test_a_refused_reply_says_nothing_and_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying(fail=True)
    pushed = capture(customer, monkeypatch)
    asyncio.run(customer.take_turn("hello"))
    assert pushed == []
    assert customer.call.turns == []


def test_a_finished_call_takes_no_more_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying("theek hai")
    customer.call.hang_up()
    pushed = capture(customer, monkeypatch)
    asyncio.run(customer.take_turn("hello"))
    assert pushed == []


def test_a_win_ends_with_a_thank_you_and_closes_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fix = verdict((Tag.APOLOGISED, "sorry"), (Tag.CONCRETE_NEXT_STEP, "raised a priority ticket"))
    customer = customer_saying("Achha.", verdicts=[fix])
    customer.call.state = replace(customer.call.state, anger=30)  # 30 − 25 = 5, with a fix
    pushed = capture(customer, monkeypatch)
    asyncio.run(customer.take_turn("sorry, i've raised a priority ticket"))
    reply, goodbye = spoken(pushed)
    assert reply == "Achha." and goodbye in ENDINGS.won
    assert states(pushed)[-1]["status"] == "won"
    assert isinstance(pushed[-1], EndWorkerFrame)  # after the last line, so it gets spoken


def test_an_insult_ends_with_the_customer_hanging_up(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying("क्या?", verdicts=[verdict((Tag.ABUSIVE, "chal nikal buddhe"))])
    pushed = capture(customer, monkeypatch)
    asyncio.run(customer.take_turn("chal nikal buddhe"))
    assert spoken(pushed)[-1] in ENDINGS.hung_up
    assert isinstance(pushed[-1], EndWorkerFrame)


def test_the_clock_ends_the_call_once_time_is_up(monkeypatch: pytest.MonkeyPatch) -> None:
    customer = customer_saying()
    pushed = capture(customer, monkeypatch)
    asyncio.run(customer.tick())
    assert pushed == []  # time left: nothing to say
    customer._started_at -= SHARMA.dynamics.time_limit_s
    asyncio.run(customer.tick())
    asyncio.run(customer.tick())
    assert customer.call.state.status == "timed_out"
    [goodbye] = spoken(pushed)
    assert goodbye in ENDINGS.timed_out
    assert sum(isinstance(frame, EndWorkerFrame) for frame in pushed) == 1  # goodbye once


def test_transcripts_become_speech_and_other_frames_pass_through() -> None:
    down, _ = asyncio.run(
        run_test(
            customer_saying("Theek hai."),
            frames_to_send=[heard("  "), TextFrame("caption"), heard("Sorry"), SleepFrame(0.5)],
            expected_down_frames=[TextFrame, TTSSpeakFrame, RTVIServerMessageFrame],
        )
    )
    assert isinstance(down[1], TTSSpeakFrame) and down[1].text == "Theek hai."


def test_speech_services_use_the_scenarios_voice_and_languages() -> None:
    stt, tts = speech_services(SHARMA, api_key="test")
    assert stt._settings.language == "en-IN"  # the trainee speaks Hinglish (S1)
    assert (tts._settings.voice, tts._settings.language) == ("Omkar", "hi-IN")
    assert tts._settings.model == "timbre-v2.5"


def test_the_speed_goes_into_gnanis_request() -> None:
    import pipecat_gnani.tts as plugin

    tts = PacedGnaniTTS(api_key="test", settings=PacedGnaniTTS.Settings(model="timbre-v2.5"))
    assert "speed" not in plugin._build_tts_payload("hi", tts._settings, 16000)
    tts.set_speed(1.12)
    assert plugin._build_tts_payload("hi", tts._settings, 16000)["speed"] == 1.12


class SlowActor:
    """Says one sentence, pauses as if thinking, then says another."""

    async def stream(self, system: str, messages: object) -> AsyncIterator[str]:
        yield "पहली बात सुनिए। "
        await asyncio.sleep(0.3)
        yield "दूसरी बात भी सुनिए।"


def test_the_customer_stops_talking_when_talked_over() -> None:
    call = Call(SHARMA, SlowActor(), ScriptedJudge([SORRY]), "hi")
    down, _ = asyncio.run(
        run_test(
            Customer(call),
            frames_to_send=[heard("sorry"), SleepFrame(0.1), InterruptionFrame(), SleepFrame(0.5)],
            expected_down_frames=[TTSSpeakFrame, InterruptionFrame, RTVIServerMessageFrame],
        )
    )
    assert isinstance(down[0], TTSSpeakFrame) and down[0].text == "पहली बात सुनिए।"
    assert call.state.anger == 65  # the turn still counts, even if the rest went unsaid


def test_the_trainee_starting_to_talk_interrupts_the_customer() -> None:
    _, turns = barge_in()
    asyncio.run(
        run_test(
            turns,
            frames_to_send=[VADUserStartedSpeakingFrame()],
            expected_down_frames=[
                VADUserStartedSpeakingFrame,
                UserStartedSpeakingFrame,
                InterruptionFrame,  # stops the voice and the rest of the reply
            ],
        )
    )


def language_request(language: str) -> RTVIClientMessageFrame:
    return RTVIClientMessageFrame(msg_id="1", type="set_language", data={"language": language})


def test_the_trainee_can_switch_to_the_customers_language() -> None:
    down, up = asyncio.run(
        run_test(
            customer_saying(),
            frames_to_send=[language_request("hi-IN")],
            expected_down_frames=[RTVIServerResponseFrame],
            expected_up_frames=[STTUpdateSettingsFrame],
        )
    )
    [response], [update] = down, up
    assert isinstance(response, RTVIServerResponseFrame) and isinstance(
        update, STTUpdateSettingsFrame
    )
    assert response.data == {"language": "hi-IN"}
    assert isinstance(update.delta, STTSettings) and update.delta.language == "hi-IN"


def test_a_language_the_scenario_doesnt_use_is_refused() -> None:
    down, up = asyncio.run(
        run_test(
            customer_saying(),
            frames_to_send=[language_request("ta-IN")],  # Sharma Uncle speaks Hindi, not Tamil
            expected_down_frames=[RTVIServerResponseFrame],
            expected_up_frames=[],
        )
    )
    [response] = down
    assert isinstance(response, RTVIServerResponseFrame)
    assert response.error == "language must be one of en-IN, hi-IN"
