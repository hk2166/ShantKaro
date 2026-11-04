"""The report card after a voice call: scores, best and worst line, and two coaching tips.

When a call's pipeline ends, the report is built in the background, because the coach's tips
take a few seconds. The browser asks for it with `GET /reports/{session_id}`.
"""

import asyncio
from collections import OrderedDict

from loguru import logger

from shant.agents.reporter import Tip, best_line, coach, score, worst_line
from shant.game.call import Call, TurnRecord
from shant.llm.provider import StructuredLLM

MAX_REPORTS = 200

# Reports by session id, oldest first. Each is a task, so a report still being written can be
# waited for.
REPORTS: OrderedDict[str, asyncio.Task[dict]] = OrderedDict()


def line_card(turn: TurnRecord | None) -> dict | None:
    if turn is None:
        return None
    return {
        "line": turn.agent,
        "tags": [str(evidence.tag) for evidence in turn.verdict.tags],
        "anger_before": turn.anger_before,
        "anger_after": turn.anger_after,
    }


def report_card(session_id: str, call: Call, tips: list[Tip]) -> dict:
    """The report as the browser shows it. A call with no turns has nothing to score."""
    scores = score(call) if call.turns else None
    return {
        "session_id": session_id,
        "scenario": call.scenario.id,
        "status": str(call.state.status),
        "final_anger": call.state.anger,
        "strikes": call.state.strikes,
        "turns": len(call.turns),
        "total": scores.total if scores else None,
        "scores": vars(scores).copy() if scores else None,
        "best_line": line_card(best_line(call)),
        "worst_line": line_card(worst_line(call)),
        "tips": [tip.model_dump() for tip in tips],
    }


async def build_report(session_id: str, call: Call, coach_llm: StructuredLLM) -> dict:
    tips: list[Tip] = []
    if call.turns:
        try:
            tips = await coach(coach_llm, call, score(call))
        except Exception:
            # The scores still stand without tips, so a coach failure must not lose the report.
            logger.exception(f"the coach failed for call {session_id}; reporting without tips")
    return report_card(session_id, call, tips)


def start_report(session_id: str, call: Call, coach_llm: StructuredLLM) -> None:
    """Start writing the report for a call that just ended, keeping the newest MAX_REPORTS."""
    REPORTS[session_id] = asyncio.create_task(build_report(session_id, call, coach_llm))
    while len(REPORTS) > MAX_REPORTS:
        REPORTS.popitem(last=False)
