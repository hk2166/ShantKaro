from pathlib import Path

from dotenv import load_dotenv
from gnani.tts import AudioConfig, GnaniTTSClient

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "out"
load_dotenv(ROOT / ".env")

LINES = {
    "hinglish_roman": "Arre bhai, mera refund teen hafte se pending hai! Aap log kar kya rahe ho?",
    "hinglish_mixed": "अरे भाई, मेरा refund तीन हफ्ते से pending है! आप लोग कर क्या रहे हो?",
}

client = GnaniTTSClient()
for name, text in LINES.items():
    audio = client.synthesize(
        text,
        voice="Poorvi",
        model="timbre-v2.5",  # the SDK default (timbre-v2.0) is rejected by the API
        language="hi-IN",
        audio_config=AudioConfig(sample_rate=16000),  # STT REST accepts at most 44.1 kHz
        output_file=OUT / f"{name}.wav",
    )
    print(f"{name}: {len(text)} chars -> {len(audio)} bytes")
