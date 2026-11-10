"""Talk to a customer by voice: browser mic → Gnani STT → customer → Gnani TTS → speaker.

Run from backend/ (needs GNANI_API_KEY and ANTHROPIC_API_KEY in .env):
  uv run python -m shant.voice.pipeline -t webrtc
  uv run python -m shant.voice.pipeline -t webrtc --scenario rohan
Then open http://localhost:7860/client, allow the mic, and talk. A browser app can instead
pick the scenario per call: POST /start with {"body": {"scenario": "rohan"}}.
GET /scenarios lists the customers, GET /reports/{session_id} gives a call's report card,
and GET /health shows how many calls are live. Limits: SHANT_MAX_LIVE_CALLS,
SHANT_CALLS_PER_DAY and SHANT_CALLS_PER_IP_PER_DAY.
"""

import argparse
import os
import random
import uuid
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat_gnani import GnaniSTTService

from shant.game.call import Call
from shant.llm.claude import COACH_SETTINGS, JUDGE_SETTINGS, ClaudeLLM
from shant.scenarios.loader import load_all
from shant.scenarios.schema import Scenario
from shant.voice.customer import Customer, state_message
from shant.voice.formatter import for_speech
from shant.voice.gnani_tts import PacedGnaniTTS
from shant.voice.reports import start_report
from shant.voice.sessions import (
    UnknownScenarioError,
    add_routes,
    claim_session,
    live_call,
    scenario_for,
    use_stun_servers,
)

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCENARIO = "sharma_uncle"
SAMPLE_RATE = 16000
TTS_MODEL = "timbre-v2.5"  # the SDK's default, timbre-v2.0, is rejected (S0)
# The customer ends the call at its time limit; past this much extra time, the bot is stopped.
HARD_STOP_GRACE_S = 30
load_dotenv(ROOT / ".env")

transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


def speech_services(scenario: Scenario, api_key: str) -> tuple[GnaniSTTService, PacedGnaniTTS]:
    """Gnani STT for the trainee and TTS in the customer's voice, as the scenario sets them."""
    stt = GnaniSTTService(
        api_key=api_key,
        sample_rate=SAMPLE_RATE,
        settings=GnaniSTTService.Settings(language=Language(scenario.voice.stt_language)),
    )
    tts = PacedGnaniTTS(
        api_key=api_key,
        sample_rate=SAMPLE_RATE,
        settings=PacedGnaniTTS.Settings(
            voice=scenario.voice.tts_voice,
            model=TTS_MODEL,
            language=Language(scenario.voice.tts_language),
        ),
    )
    return stt, tts


def barge_in() -> tuple[VADProcessor, UserTurnProcessor]:
    """Hear the trainee start talking, so the customer stops and listens (barge-in).

    Gnani's STT sends only final transcripts, so a local voice detector (Silero) notices
    speech, and the turn processor turns that into an interruption: the voice stops and the
    rest of the reply is dropped.
    """
    turns = UserTurnStrategies(
        start=[VADUserTurnStartStrategy()],
        stop=[SpeechTimeoutUserTurnStopStrategy(wait_for_transcript=False)],
    )
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer())
    return vad, UserTurnProcessor(user_turn_strategies=turns)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments, scenario: Scenario):
    call = Call(
        scenario, ClaudeLLM(), ClaudeLLM(JUDGE_SETTINGS), random.choice(scenario.opening_lines)
    )
    stt, tts = speech_services(scenario, os.environ["GNANI_API_KEY"])
    customer = Customer(call, set_speed=tts.set_speed)
    vad, turns = barge_in()
    pipeline = Pipeline([transport.input(), vad, stt, turns, customer, tts, transport.output()])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client) -> None:
        logger.info(f"call started with {scenario.persona.name}")
        await task.queue_frames(
            [state_message(call), TTSSpeakFrame(for_speech(call.actor.opening_line))]
        )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client) -> None:
        call.hang_up()  # no-op if the call already ended on its own
        logger.info(f"call ended: {call.state.status}, anger {call.state.anger}")
        await task.cancel()

    session_id = runner_args.session_id or str(uuid.uuid4())
    stop_after_s = scenario.dynamics.time_limit_s + HARD_STOP_GRACE_S

    def write_report() -> None:
        start_report(session_id, call, ClaudeLLM(COACH_SETTINGS))

    async with live_call(session_id, call, task.cancel, stop_after_s, on_end=write_report):
        await PipelineRunner(handle_sigint=runner_args.handle_sigint).run(task)


async def bot(runner_args: RunnerArguments) -> None:
    """Entry point the Pipecat runner calls for each new connection."""
    args = runner_args.cli_args
    if runner_args.session_id and not claim_session(runner_args.session_id):
        logger.warning(f"call not started: session {runner_args.session_id} already has a bot")
        return
    try:
        scenario = scenario_for(runner_args.body, args.scenario if args else DEFAULT_SCENARIO)
    except UnknownScenarioError as error:
        logger.error(f"call not started: {error}")
        return
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args, scenario)


if __name__ == "__main__":
    from pipecat.runner.run import app, main

    add_routes(app)
    if stun := use_stun_servers():
        logger.info(f"WebRTC STUN servers: {stun}")
    parser = argparse.ArgumentParser(description="Shant Karo voice call")
    parser.add_argument("--scenario", choices=sorted(load_all()), default=DEFAULT_SCENARIO)
    main(parser)
