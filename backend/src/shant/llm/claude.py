"""Claude through the Anthropic SDK, configured as decided in ADR-003."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

import anthropic

from shant.llm.provider import LLMRefusalError, Message, T

# Models that accept server-side `fallbacks: "default"`; others reject the parameter.
FALLBACK_MODELS = frozenset(
    {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
)


@dataclass(frozen=True)
class ClaudeSettings:
    model: str = "claude-sonnet-5-5"
    effort: str | None = "low"
    thinking: str | None = "between_tools"
    max_tokens: int = 2048


JUDGE_SETTINGS = ClaudeSettings(
    model="claude-opus-5-5", effort="medium", thinking=None, max_tokens=8000
)

COACH_SETTINGS = ClaudeSettings(
    model="claude-opus-5-5", effort="low", thinking=None, max_tokens=8000
)


def request_params(
    settings: ClaudeSettings, system: str, messages: Sequence[Message]
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": system,
        "messages": [{"role": m.role, "content": m.text} for m in messages],
    }
    if settings.effort:
        params["output_config"] = {"effort": settings.effort}
    if settings.thinking:
        params["thinking"] = {"type": settings.thinking}
    if settings.model in FALLBACK_MODELS:
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"
    return params


class ClaudeLLM:
    def __init__(
        self,
        settings: ClaudeSettings | None = None,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.settings = settings or ClaudeSettings()
        self._client = client or anthropic.AsyncAnthropic()

    async def stream(self, system: str, messages: Sequence[Message]) -> AsyncIterator[str]:
        params = request_params(self.settings, system, messages)
        async with self._client.beta.messages.stream(**params) as stream:
            async for text in stream.text_stream:
                yield text
            final = await stream.get_final_message()
        if final.stop_reason == "refusal":
            raise LLMRefusalError(f"{self.settings.model} declined to reply")

    async def parse(self, system: str, messages: Sequence[Message], schema: type[T]) -> T:
        params = request_params(self.settings, system, messages)
        response = await self._client.beta.messages.parse(**params, output_format=schema)
        if response.stop_reason == "refusal":
            raise LLMRefusalError(f"{self.settings.model} declined to reply")
        if response.parsed_output is None:
            raise ValueError("no structured output")
        return response.parsed_output
