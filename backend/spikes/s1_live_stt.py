"""S1: stream audio to Gnani realtime STT and print each transcript.

Run from backend/:
  uv run python spikes/s1_live_stt.py                          # live mic, hi-IN, 600 ms
  uv run python spikes/s1_live_stt.py --lang en-IN --silence 400
  uv run python spikes/s1_live_stt.py --lang en-IN --format transcribe   # numbers as digits
  uv run python spikes/s1_live_stt.py --file out/s1/sentence_00.wav
"""

import argparse
import asyncio
import json
import os
import struct
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import sounddevice as sd
import websockets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

URL = "wss://api.vachana.ai/stt/v3/stream"
SAMPLE_RATE = 16_000
FRAME_BYTES = 1024  # 512 int16 samples, the exact frame size Gnani requires
FRAME_SECONDS = FRAME_BYTES / 2 / SAMPLE_RATE
TAIL_SECONDS = 2


@dataclass
class Transcript:
    text: str
    received_at: float
    server_latency_ms: int
    speech_ms: int


def stt_headers(lang: str, silence_ms: int, fmt: str = "verbatim") -> dict[str, str]:
    return {
        "x-api-key-id": os.environ["GNANI_API_KEY"],
        "lang_code": lang,
        "x-sample-rate": str(SAMPLE_RATE),
        "x-vad-threshold": "0.5",
        "x-min-silence-ms": str(silence_ms),
        "x-format": fmt,
    }


def load_pcm(path: Path) -> bytes:
    """Return the samples of a 16 kHz mono 16-bit WAV, ignoring its declared data length."""
    raw = path.read_bytes()
    channels, rate, _, _, bits = struct.unpack("<HIIHH", raw[22:36])
    if (channels, rate, bits) != (1, SAMPLE_RATE, 16):
        raise ValueError(f"{path}: need 16 kHz mono 16-bit, got {rate} Hz {channels} ch {bits} bit")
    return raw[raw.index(b"data") + 8 :]


async def mic_frames() -> AsyncIterator[bytes]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_audio(indata, _frames, _time_info, status) -> None:
        if status:
            print(status)
        loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_BYTES // 2,
        callback=on_audio,
    ):
        while True:
            yield await queue.get()


async def paced_frames(pcm: bytes) -> AsyncIterator[bytes]:
    """Yield PCM in frames at real-time pace, the way a microphone delivers it."""
    start = time.monotonic()
    for index, offset in enumerate(range(0, len(pcm), FRAME_BYTES)):
        await asyncio.sleep(max(0.0, start + index * FRAME_SECONDS - time.monotonic()))
        yield pcm[offset : offset + FRAME_BYTES].ljust(FRAME_BYTES, b"\0")


def print_transcript(transcript: Transcript) -> None:
    print(transcript.text)
    print(f"   speech {transcript.speech_ms} ms, server latency {transcript.server_latency_ms} ms")


async def transcribe_stream(
    frames: AsyncIterator[bytes],
    lang: str,
    silence_ms: int,
    on_transcript: Callable[[Transcript], None] = print_transcript,
    fmt: str = "verbatim",
) -> tuple[float, list[Transcript]]:
    """Stream frames to Gnani. Returns when the first frame was sent, and every transcript."""
    transcripts: list[Transcript] = []
    first_frame_at = 0.0
    async with websockets.connect(URL, additional_headers=stt_headers(lang, silence_ms, fmt)) as ws:
        hello = json.loads(await ws.recv())
        if hello.get("type") != "connected":
            raise RuntimeError(f"unexpected first message: {hello}")

        async def send() -> None:
            nonlocal first_frame_at
            async for frame in frames:
                if not first_frame_at:
                    first_frame_at = time.monotonic()
                await ws.send(frame)
            # Trailing silence lets the server's VAD close the last segment before we hang up.
            async for frame in paced_frames(bytes(TAIL_SECONDS * SAMPLE_RATE * 2)):
                await ws.send(frame)
            await ws.close()

        async def receive() -> None:
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "transcript":
                    transcript = Transcript(
                        msg["text"], time.monotonic(), msg["latency"], msg["audio_duration_ms"]
                    )
                    transcripts.append(transcript)
                    on_transcript(transcript)
                elif msg["type"] == "error":
                    print(f"STT error: {msg.get('message')}")

        await asyncio.gather(send(), receive())
    return first_frame_at, transcripts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--lang", default="hi-IN")
    parser.add_argument("--silence", type=int, default=600, help="x-min-silence-ms")
    parser.add_argument(
        "--format",
        default="verbatim",
        choices=["verbatim", "transcribe"],
        help="transcribe turns spoken numbers and money into digits (ITN)",
    )
    parser.add_argument("--file", type=Path, help="16 kHz mono WAV to stream instead of the mic")
    args = parser.parse_args()

    frames = paced_frames(load_pcm(args.file)) if args.file else mic_frames()
    print(f"Streaming {args.file or 'mic'} ({args.lang}, silence {args.silence} ms). Ctrl+C stops.")
    asyncio.run(transcribe_stream(frames, args.lang, args.silence, fmt=args.format))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
