"""S1 step A: check the mic delivers 1,024-byte blocks at 16 kHz and isn't silent."""

from array import array

import sounddevice as sd

SECONDS = 3
stats = {"blocks": 0, "block_bytes": 0, "peak": 0}


def on_audio(indata, frames, time_info, status) -> None:
    data = bytes(indata)
    stats["blocks"] += 1
    stats["block_bytes"] = len(data)
    stats["peak"] = max(stats["peak"], max(abs(sample) for sample in array("h", data)))


stream = sd.RawInputStream(
    samplerate=16000,
    channels=1,
    dtype="int16",
    blocksize=512,
    callback=on_audio,
)

print(f"Recording {SECONDS} s, say something...")
with stream:
    sd.sleep(SECONDS * 1000)

print(f"blocks: {stats['blocks']} (expected about {16000 * SECONDS // 512})")
print(f"bytes per block: {stats['block_bytes']} (expected 1024)")
print(f"peak level: {stats['peak']} (0 means the mic is blocked or muted)")
