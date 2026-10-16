import asyncio
from collections.abc import Sequence

from shant.agents.judge import TagEvidence, Verdict, judge, system_prompt
from shant.engine.state import Judgement
from shant.llm.provider import Message, T
from shant.scenarios.loader import load_all
from shant.tags import Tag

SCENARIOS = load_all()
SHARMA = SCENARIOS["sharma_uncle"]
LAKSHMI = SCENARIOS["lakshmi_aunty"]
LINE = "sharma ji i am really sorry aapko teen hafte wait karna pada"


def verdict(*pairs: tuple[Tag, str]) -> Verdict:
    return Verdict(tags=[TagEvidence(tag=tag, quote=quote) for tag, quote in pairs])


def test_a_tag_whose_quote_is_in_the_line_is_kept() -> None:
    grounded = verdict((Tag.APOLOGISED, "really sorry")).grounded_in(LINE)
    assert grounded.judgement() == Judgement(frozenset({Tag.APOLOGISED}))


def test_a_tag_with_an_invented_quote_is_dropped() -> None:
    grounded = verdict((Tag.CONCRETE_NEXT_STEP, "refund in 48 hours")).grounded_in(LINE)
    assert grounded.tags == []


def test_quotes_match_ignoring_case_and_extra_spaces() -> None:
    grounded = verdict((Tag.USED_NAME, "Sharma   Ji")).grounded_in(LINE)
    assert grounded.judgement() == Judgement(frozenset({Tag.USED_NAME}))


def test_an_empty_quote_is_dropped() -> None:
    assert verdict((Tag.APOLOGISED, "  ")).grounded_in(LINE).tags == []


def test_prompt_lists_the_scenarios_policy() -> None:
    prompt = system_prompt(SHARMA, language_switched=False)
    for text in [*SHARMA.policy.allowed_remedies, *SHARMA.policy.forbidden_promises]:
        assert text in prompt
    assert "$" not in prompt


def test_prompt_says_whether_the_customer_switched_language() -> None:
    assert "has not switched" in system_prompt(LAKSHMI, language_switched=False)
    assert "switched to speaking Tamil" in system_prompt(LAKSHMI, language_switched=True)


class FakeJudgeLLM:
    def __init__(self, answer: Verdict) -> None:
        self.answer = answer
        self.calls: list[tuple[str, list[Message]]] = []

    async def parse(self, system: str, messages: Sequence[Message], schema: type[T]) -> T:
        self.calls.append((system, list(messages)))
        return schema.model_validate(self.answer.model_dump())


def test_judge_sends_both_lines_and_returns_a_grounded_verdict() -> None:
    llm = FakeJudgeLLM(verdict((Tag.APOLOGISED, "really sorry"), (Tag.DISMISSIVE, "calm down")))
    result = asyncio.run(judge(llm, SHARMA, "मेरा refund कहाँ है?", LINE, language_switched=False))
    assert result.judgement() == Judgement(frozenset({Tag.APOLOGISED}))
    ((system, messages),) = llm.calls
    assert system == system_prompt(SHARMA, language_switched=False)
    assert messages == [
        Message("user", f"Customer's last line: मेरा refund कहाँ है?\nAgent's line to judge: {LINE}")
    ]
