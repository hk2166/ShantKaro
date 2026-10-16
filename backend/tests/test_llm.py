import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import BaseModel

from shant.llm.claude import JUDGE_SETTINGS, ClaudeLLM, ClaudeSettings, request_params
from shant.llm.provider import LLMRefusalError, Message

HISTORY = [Message("user", "hello"), Message("assistant", "hi"), Message("user", "sorry")]


def test_default_request_matches_adr_003() -> None:
    params = request_params(ClaudeSettings(), "be Sharma Uncle", HISTORY)
    assert params["model"] == "claude-sonnet-5-5"
    assert params["output_config"] == {"effort": "low"}
    assert params["thinking"] == {"type": "between_tools"}
    assert params["fallbacks"] == "default"
    assert params["betas"] == ["server-side-fallback-2026-07-01"]
    assert params["system"] == "be Sharma Uncle"
    assert params["messages"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "sorry"},
    ]


def test_effort_and_thinking_can_be_left_out() -> None:
    params = request_params(ClaudeSettings(effort=None, thinking=None), "s", HISTORY)
    assert "output_config" not in params
    assert "thinking" not in params


def test_models_without_server_fallbacks_get_no_fallback_params() -> None:
    params = request_params(ClaudeSettings(model="claude-haiku-5-5"), "s", HISTORY)
    assert "fallbacks" not in params
    assert "betas" not in params


class FakeStream:
    def __init__(self, chunks: list[str], stop_reason: str) -> None:
        self.chunks = chunks
        self.stop_reason = stop_reason

    async def __aenter__(self) -> "FakeStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    @property
    def text_stream(self):
        async def chunks():
            for chunk in self.chunks:
                yield chunk

        return chunks()

    async def get_final_message(self) -> SimpleNamespace:
        return SimpleNamespace(stop_reason=self.stop_reason)


def fake_client(stream: FakeStream) -> tuple[Any, list[dict]]:
    calls: list[dict] = []

    def open_stream(**params: Any) -> FakeStream:
        calls.append(params)
        return stream

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=open_stream)))
    return cast(Any, client), calls


async def collect(llm: ClaudeLLM) -> str:
    return "".join([chunk async for chunk in llm.stream("system", HISTORY)])


def test_stream_yields_the_reply_and_sends_the_built_request() -> None:
    client, calls = fake_client(FakeStream(["अरे ", "Rahul जी!"], "end_turn"))
    assert asyncio.run(collect(ClaudeLLM(client=client))) == "अरे Rahul जी!"
    assert calls == [request_params(ClaudeSettings(), "system", HISTORY)]


def test_a_refusal_raises_after_the_stream() -> None:
    client, _ = fake_client(FakeStream([], "refusal"))
    with pytest.raises(LLMRefusalError):
        asyncio.run(collect(ClaudeLLM(client=client)))


class Answer(BaseModel):
    ok: bool


def fake_parse_client(parsed: Answer | None, stop_reason: str) -> tuple[Any, list[dict]]:
    calls: list[dict] = []

    async def parse(**params: Any) -> SimpleNamespace:
        calls.append(params)
        return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    return cast(Any, client), calls


def test_parse_returns_the_validated_object_and_sends_the_schema() -> None:
    client, calls = fake_parse_client(Answer(ok=True), "end_turn")
    result = asyncio.run(ClaudeLLM(JUDGE_SETTINGS, client).parse("s", HISTORY, Answer))
    assert result == Answer(ok=True)
    assert calls[0]["output_format"] is Answer
    assert calls[0]["model"] == "claude-opus-5-5"
    assert calls[0]["output_config"] == {"effort": "medium"}
    assert "thinking" not in calls[0]


def test_parse_raises_on_a_refusal() -> None:
    client, _ = fake_parse_client(None, "refusal")
    with pytest.raises(LLMRefusalError):
        asyncio.run(ClaudeLLM(JUDGE_SETTINGS, client).parse("s", HISTORY, Answer))


def test_parse_raises_when_nothing_was_parsed() -> None:
    client, _ = fake_parse_client(None, "end_turn")
    with pytest.raises(ValueError, match="no structured output"):
        asyncio.run(ClaudeLLM(JUDGE_SETTINGS, client).parse("s", HISTORY, Answer))
