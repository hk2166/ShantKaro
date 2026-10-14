"""S4 (part 1): talk to a Pipecat bot in your browser over WebRTC. No LLM yet.

Run from backend/:
  uv run python spikes/s4_echo_bot.py -t webrtc
Then open http://localhost:7860/client, allow the mic, and talk. The bot repeats what Gnani
heard, so you can judge the full voice loop (WebRTC -> Gnani STT -> Gnani TTS -> WebRTC)
before an LLM is added on Day 6.
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import Frame, TranscriptionFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat_gnani import GnaniSTTService, GnaniTTSService

load_dotenv()

transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


class EchoProcessor(FrameProcessor):
    """Replaces each final transcript with a spoken 'You said: ...'."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            # Real mics produce empty transcripts from breaths and noise (S1).
            if text:
                logger.info(f"heard: {text}")
                await self.push_frame(TTSSpeakFrame(f"You said: {text}"))
            return
        await self.push_frame(frame, direction)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    api_key = os.environ["GNANI_API_KEY"]
    stt = GnaniSTTService(
        api_key=api_key,
        sample_rate=16000,
        settings=GnaniSTTService.Settings(language=Language.EN_IN),
    )
    tts = GnaniTTSService(
        api_key=api_key,
        sample_rate=16000,
        settings=GnaniTTSService.Settings(
            voice="Kaveri", model="timbre-v2.5", language=Language.EN_IN
        ),
    )

    pipeline = Pipeline([transport.input(), stt, EchoProcessor(), tts, transport.output()])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client) -> None:
        logger.info("client connected")
        await task.queue_frames([TTSSpeakFrame("Hello! Say something and I will repeat it.")])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client) -> None:
        logger.info("client disconnected")
        await task.cancel()

    await PipelineRunner(handle_sigint=runner_args.handle_sigint).run(task)


async def bot(runner_args: RunnerArguments) -> None:
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
