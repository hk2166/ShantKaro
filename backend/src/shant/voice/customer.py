"""The customer's side of a voice call, as a step in the Pipecat pipeline.

It takes each final transcript of the trainee, runs one turn of the `Call` (the customer
replies while the Judge labels the line), and sends the reply to the voice one sentence at a
time, so the customer starts talking before the whole reply is written.
"""

import asyncio
import time

from loguru import logger
from pipecat.frames.frames import Frame, TranscriptionFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from shant.game.call import Call
from shant.llm.provider import LLMRefusalError
from shant.voice.formatter import SentenceBuffer, for_speech


class Customer(FrameProcessor):
    def __init__(self, call: Call) -> None:
        super().__init__()
        self.call = call
        self._started_at = time.monotonic()
        # The trainee may speak again while the customer is still replying. Turns must not
        # overlap, or the conversation history gets mixed up.
        self._one_turn_at_a_time = asyncio.Lock()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            line = frame.text.strip()
            # Real mics produce empty transcripts from breaths and noise (S1).
            if line:
                # Reply in a task, so frames keep flowing while the LLMs work.
                self.create_task(self.take_turn(line.lower()))
            return
        await self.push_frame(frame, direction)

    async def take_turn(self, agent_line: str) -> None:
        async with self._one_turn_at_a_time:
            if self.call.state.finished:
                return
            sentences: asyncio.Queue[str | None] = asyncio.Queue()
            buffer = SentenceBuffer()

            def on_text(chunk: str) -> None:
                for sentence in buffer.feed(chunk):
                    sentences.put_nowait(sentence)

            def on_reply_done() -> None:
                for sentence in buffer.flush():
                    sentences.put_nowait(sentence)
                sentences.put_nowait(None)

            elapsed = time.monotonic() - self._started_at
            turn = asyncio.create_task(
                self.call.respond(agent_line, elapsed, on_text, on_reply_done)
            )
            # If the reply fails before it finishes, stop waiting for more sentences.
            turn.add_done_callback(lambda _: sentences.put_nowait(None))
            try:
                while (sentence := await sentences.get()) is not None:
                    if spoken := for_speech(sentence):
                        await self.push_frame(TTSSpeakFrame(spoken))
                record = await turn
            except LLMRefusalError:
                logger.warning("the customer declined to reply; waiting for the next line")
                return
            finally:
                turn.cancel()
            tags = ", ".join(evidence.tag for evidence in record.verdict.tags) or "no tags"
            logger.info(
                f"judge: {tags} → anger {record.anger_before} → {record.anger_after} "
                f"({self.call.state.status})"
            )
