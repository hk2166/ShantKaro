"""The customer's side of a voice call, as a step in the Pipecat pipeline.

It takes each final transcript of the trainee, runs one turn of the `Call` (the customer
replies while the Judge labels the line), and sends the reply to the voice one sentence at a
time, so the customer starts talking before the whole reply is written.

It also runs the call clock, sends the call's state to the browser after every change, sets
the voice's speed from the customer's anger, and ends the call with a last line from the
customer when they win, hang up or run out of time.

When the trainee talks over the customer, the rest of the reply is dropped. When the browser
asks for another language, the speech-to-text switches to it.
"""

import asyncio
import time
from collections.abc import Callable

from loguru import logger
from pipecat.frames.frames import (
    EndWorkerFrame,
    Frame,
    InterruptionFrame,
    StartFrame,
    STTUpdateSettingsFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import (
    RTVIClientMessageFrame,
    RTVIServerMessageFrame,
    RTVIServerResponseFrame,
)
from pipecat.services.settings import STTSettings
from pipecat.transcriptions.language import Language

from shant.game.call import Call
from shant.llm.provider import LLMRefusalError
from shant.voice.formatter import SentenceBuffer, for_speech

CLOCK_TICK_S = 1.0


def state_message(call: Call) -> RTVIServerMessageFrame:
    """The call's state for the browser, which shows the anger meter, timer and strikes."""
    return RTVIServerMessageFrame(data={"type": "call_state", **call.snapshot()})


class Customer(FrameProcessor):
    def __init__(self, call: Call, set_speed: Callable[[float], None] = lambda _: None) -> None:
        super().__init__()
        self.call = call
        self._set_speed = set_speed
        self._started_at = time.monotonic()
        self._call_timer: asyncio.Task | None = None
        self._said_goodbye = False
        # Counts the times the trainee started talking. A reply stops being spoken as soon as
        # this changes, so the customer goes quiet when talked over (barge-in).
        self._interruptions = 0
        # The trainee may speak again while the customer is still replying. Turns must not
        # overlap, or the conversation history gets mixed up. The clock waits its turn too.
        self._one_turn_at_a_time = asyncio.Lock()
        self._match_speed_to_anger()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            self._interruptions += 1
        if isinstance(frame, RTVIClientMessageFrame) and frame.type == "set_language":
            await self._switch_language(frame)
            return
        if isinstance(frame, TranscriptionFrame):
            line = frame.text.strip()
            # Real mics produce empty transcripts from breaths and noise (S1).
            if line:
                # Reply in a task, so frames keep flowing while the LLMs work.
                self.create_task(self.take_turn(line.lower()))
            return
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self._started_at = time.monotonic()
            self._call_timer = self.create_task(self._run_call_timer())

    async def cleanup(self) -> None:
        await super().cleanup()
        if self._call_timer:
            await self.cancel_task(self._call_timer)

    def elapsed(self) -> float:
        return time.monotonic() - self._started_at

    async def take_turn(self, agent_line: str) -> None:
        async with self._one_turn_at_a_time:
            if self.call.state.finished:
                return
            sentences: asyncio.Queue[str | None] = asyncio.Queue()
            buffer = SentenceBuffer()
            interruptions_before = self._interruptions

            def on_text(chunk: str) -> None:
                for sentence in buffer.feed(chunk):
                    sentences.put_nowait(sentence)

            def on_reply_done() -> None:
                for sentence in buffer.flush():
                    sentences.put_nowait(sentence)
                sentences.put_nowait(None)

            turn = asyncio.create_task(
                self.call.respond(agent_line, self.elapsed(), on_text, on_reply_done)
            )
            # If the reply fails before it finishes, stop waiting for more sentences.
            turn.add_done_callback(lambda _: sentences.put_nowait(None))
            try:
                while (sentence := await sentences.get()) is not None:
                    talked_over = self._interruptions != interruptions_before
                    if (spoken := for_speech(sentence)) and not talked_over:
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
            # The reply above was already spoken at the old speed; the next one uses the new.
            self._match_speed_to_anger()
            await self.push_frame(state_message(self.call))
            await self._end_if_finished()

    async def tick(self) -> None:
        """Move the call clock on. Ends the call when time runs out."""
        async with self._one_turn_at_a_time:
            self.call.tick(self.elapsed())
            await self._end_if_finished()

    async def _run_call_timer(self) -> None:
        while not self.call.state.finished:
            await asyncio.sleep(CLOCK_TICK_S)
            await self.tick()

    async def _switch_language(self, message: RTVIClientMessageFrame) -> None:
        """Make the speech-to-text listen for the language the trainee chose in the browser."""
        data = message.data if isinstance(message.data, dict) else {}
        language = data.get("language")
        allowed = self.call.scenario.trainee_languages
        if language not in allowed:
            error = f"language must be one of {', '.join(allowed)}"
            await self.push_frame(RTVIServerResponseFrame(client_msg=message, error=error))
            return
        logger.info(f"the trainee now speaks {language}")
        # The speech-to-text is before this step in the pipeline, so the change goes upstream.
        update = STTUpdateSettingsFrame(delta=STTSettings(language=Language(language)))
        await self.push_frame(update, FrameDirection.UPSTREAM)
        await self.push_frame(
            RTVIServerResponseFrame(client_msg=message, data={"language": language})
        )

    def _match_speed_to_anger(self) -> None:
        voice = self.call.scenario.voice
        self._set_speed(voice.band_for(self.call.state.anger).tts_speed)

    async def _end_if_finished(self) -> None:
        if not self.call.state.finished or self._said_goodbye:
            return
        self._said_goodbye = True
        status = self.call.state.status
        logger.info(f"call over: {status}, anger {self.call.state.anger}")
        if line := self.call.closing_line():
            await self.push_frame(TTSSpeakFrame(for_speech(line)))
        await self.push_frame(state_message(self.call))
        # Ends the pipeline once everything queued ahead of it, the last line included, has
        # been spoken.
        await self.push_frame(EndWorkerFrame(reason=str(status)))
