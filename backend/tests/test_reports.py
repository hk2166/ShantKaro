import asyncio

from fakes import ScriptedActor, ScriptedCoach, ScriptedJudge

from shant.agents.judge import TagEvidence, Verdict
from shant.agents.reporter import Tip
from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.tags import Tag
from shant.voice.reports import MAX_REPORTS, REPORTS, build_report, start_report

SHARMA = load_all()["sharma_uncle"]
SORRY = Verdict(tags=[TagEvidence(tag=Tag.APOLOGISED, quote="sorry")])
TIP = Tip(quote="sorry", advice="Name the delay.", try_saying="Three weeks is too long, sir.")


def played_call(*lines: str) -> Call:
    call = Call(
        SHARMA, ScriptedActor(["Hmm."] * len(lines)), ScriptedJudge([SORRY] * len(lines)), "hi"
    )
    for line in lines:
        asyncio.run(call.respond(line, 15))
    return call


def test_the_report_has_scores_lines_and_tips() -> None:
    call = played_call("sorry sharma ji")
    call.hang_up()
    report = asyncio.run(build_report("s1", call, ScriptedCoach([TIP])))
    assert report["session_id"] == "s1" and report["scenario"] == "sharma_uncle"
    assert (report["status"], report["final_anger"], report["strikes"], report["turns"]) == (
        "ended_by_trainee",
        65,
        0,
        1,
    )
    assert set(report["scores"]) == {
        "empathy",
        "resolution",
        "policy_compliance",
        "language_adaptation",
        "efficiency",
    }
    assert isinstance(report["total"], int)
    assert report["best_line"] == {
        "line": "sorry sharma ji",
        "tags": ["apologised"],
        "anger_before": 75,
        "anger_after": 65,
    }
    assert report["worst_line"] is None
    assert report["tips"] == [TIP.model_dump()]


def test_a_call_with_no_turns_has_nothing_to_score() -> None:
    call = played_call()
    call.hang_up()
    report = asyncio.run(build_report("s2", call, ScriptedCoach([TIP])))
    assert report["turns"] == 0
    assert (report["total"], report["scores"], report["best_line"], report["worst_line"]) == (
        None,
        None,
        None,
        None,
    )
    assert report["tips"] == []


def test_the_report_survives_a_coach_that_fails() -> None:
    report = asyncio.run(build_report("s3", played_call("sorry"), ScriptedCoach([], fail=True)))
    assert report["tips"] == [] and report["total"] is not None


def test_only_the_newest_reports_are_kept() -> None:
    call = played_call()

    async def run() -> None:
        for number in range(MAX_REPORTS + 5):
            start_report(f"r{number}", call, ScriptedCoach([]))
        await asyncio.gather(*REPORTS.values())

    asyncio.run(run())
    assert len(REPORTS) == MAX_REPORTS
    assert "r0" not in REPORTS and f"r{MAX_REPORTS + 4}" in REPORTS
