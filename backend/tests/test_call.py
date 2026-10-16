import asyncio
import json
from pathlib import Path

import pytest
from fakes import ScriptedActor, ScriptedJudge

from shant.agents.judge import TagEvidence, Verdict
from shant.engine.state import GameState, Status
from shant.game.call import Call, CallOverError
from shant.llm.provider import LLMRefusalError, Message
from shant.scenarios.loader import load_all
from shant.tags import Tag

SCENARIOS = load_all()
SHARMA = SCENARIOS["sharma_uncle"]
TRANSCRIPTS = sorted((Path(__file__).resolve().parents[2] / "evals" / "transcripts").glob("*.json"))


def verdict(*pairs: tuple[Tag, str]) -> Verdict:
    return Verdict(tags=[TagEvidence(tag=tag, quote=quote) for tag, quote in pairs])


SORRY = verdict((Tag.APOLOGISED, "really sorry"))


def new_call(customer: list[str], verdicts: list[Verdict], fail: bool = False) -> Call:
    return Call(SHARMA, ScriptedActor(customer, fail), ScriptedJudge(verdicts), "opening line")


def test_a_turn_streams_the_reply_records_it_and_applies_the_judgement() -> None:
    call = new_call(["तीन हफ्ते हो गए!"], [SORRY])
    streamed: list[str] = []
    record = asyncio.run(call.respond("i am really sorry", 15, on_text=streamed.append))
    assert "".join(streamed).strip() == "तीन हफ्ते हो गए!"
    assert record.customer == "तीन हफ्ते हो गए!"
    assert (record.anger_before, record.anger_after) == (75, 65)
    assert call.state.anger == 65
    assert call.history == [
        Message("user", "i am really sorry"),
        Message("assistant", "तीन हफ्ते हो गए!"),
    ]


def test_the_judge_sees_the_previous_customer_line() -> None:
    judge_llm = ScriptedJudge([SORRY, SORRY])
    call = Call(SHARMA, ScriptedActor(["first reply", "second reply"]), judge_llm, "opening line")

    async def two_turns() -> None:
        await call.respond("i am really sorry", 15)
        await call.respond("really sorry again", 30)

    asyncio.run(two_turns())
    assert "Customer's last line: opening line" in judge_llm.calls[0][0].text
    assert "Customer's last line: first reply" in judge_llm.calls[1][0].text


def test_the_customer_replies_from_the_state_before_this_turns_judgement() -> None:
    actor = ScriptedActor(["reply"])
    call = Call(SHARMA, actor, ScriptedJudge([SORRY]), "opening line")
    asyncio.run(call.respond("i am really sorry", 15))
    assert "anger is 75 out of 100" in actor.systems[0]
    assert call.state.anger == 65


def test_stage_directions_are_removed_from_the_saved_reply() -> None:
    call = new_call(["*sighs* theek hai"], [verdict()])
    assert asyncio.run(call.respond("hello", 15)).customer == "theek hai"


def test_a_failed_reply_leaves_the_history_unchanged() -> None:
    call = new_call([], [SORRY], fail=True)
    with pytest.raises(LLMRefusalError):
        asyncio.run(call.respond("i am really sorry", 15))
    assert call.history == []
    assert call.state.anger == 75


def test_a_finished_call_takes_no_more_turns() -> None:
    call = new_call(["bye"], [verdict()])
    call.hang_up()
    assert call.state.status is Status.ENDED_BY_TRAINEE
    with pytest.raises(CallOverError):
        asyncio.run(call.respond("hello", 15))


def test_the_clock_can_end_the_call_between_turns() -> None:
    call = new_call([], [])
    call.tick(SHARMA.dynamics.time_limit_s)
    assert call.state.status is Status.TIMED_OUT


def test_the_transcript_is_plain_json() -> None:
    call = new_call(["reply"], [SORRY])
    asyncio.run(call.respond("i am really sorry", 15))
    data = json.loads(json.dumps(call.transcript(), ensure_ascii=False))
    assert data["scenario"] == "sharma_uncle"
    assert data["turns"][0]["tags"] == [{"tag": "apologised", "quote": "really sorry"}]
    assert data["turns"][0]["language_switched"] is False


@pytest.mark.parametrize("path", TRANSCRIPTS, ids=lambda p: p.stem)
def test_replaying_a_saved_transcript_reaches_the_same_ending(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = data["turns"]
    verdicts = [Verdict(tags=[TagEvidence(**e) for e in turn["tags"]]) for turn in turns]
    call = Call(
        SCENARIOS[data["scenario"]],
        ScriptedActor([turn["customer"] for turn in turns]),
        ScriptedJudge(verdicts),
        data["opening_line"],
    )

    async def replay() -> GameState:
        for turn in turns:
            record = await call.respond(turn["agent"], turn["elapsed_s"])
            assert (record.anger_before, record.anger_after) == (
                turn["anger_before"],
                turn["anger_after"],
            )
        return call.state

    final = asyncio.run(replay())
    assert str(final.status) == data["status"]
    assert final.anger == data["final_anger"]
