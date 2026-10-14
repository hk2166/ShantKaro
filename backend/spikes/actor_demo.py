"""Day 9 check: the same agent line, answered by each customer at anger 30 and anger 90.

Run from backend/ (needs ANTHROPIC_API_KEY in .env):
  uv run python spikes/actor_demo.py
"""

import asyncio
import time
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from shant.agents.actor import Actor
from shant.engine.rules import start
from shant.llm.claude import ClaudeLLM
from shant.llm.provider import Message
from shant.scenarios.loader import load_all
from shant.voice.formatter import for_speech

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

AGENT_LINE = "i understand your problem let me check what i can do for you"


async def main() -> None:
    llm = ClaudeLLM()
    for scenario in load_all().values():
        actor = Actor(scenario, llm, scenario.opening_lines[0])
        print(f"\n=== {scenario.persona.name} | agent: {AGENT_LINE}")
        for anger in (30, 90):
            state = replace(start(scenario), anger=anger)
            started = time.perf_counter()
            reply = "".join([c async for c in actor.reply(state, [Message("user", AGENT_LINE)])])
            elapsed = (time.perf_counter() - started) * 1000
            spoken = for_speech(reply)
            words = len(spoken.split())
            print(f"  anger {anger} ({elapsed:.0f} ms, {words} words): {spoken}")


if __name__ == "__main__":
    asyncio.run(main())
