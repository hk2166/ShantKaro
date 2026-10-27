"""Gnani's TTS at a speed the customer's anger can change during the call.

pipecat-gnani 0.5.12 has no speed setting, but Gnani's API accepts `speed` (0.85–1.15) with
timbre-v2.5, and Gnani's own SDK sends it in the same request. The plugin builds every request
in `_build_tts_payload`, so we wrap that one function to add the speed kept in the settings'
`extra` dict. Remove this module when the plugin supports speed.
"""

from typing import Any

import pipecat_gnani.tts as plugin
from pipecat_gnani import GnaniTTSService

_plugin_payload = plugin._build_tts_payload


def _payload_with_speed(text: str, settings: Any, sample_rate: int) -> dict:
    payload = _plugin_payload(text, settings, sample_rate)
    if (speed := settings.extra.get("speed")) is not None:
        payload["speed"] = speed
    return payload


plugin._build_tts_payload = _payload_with_speed


class PacedGnaniTTS(GnaniTTSService):
    def set_speed(self, speed: float) -> None:
        """Speak every sentence from now on at this speed (1.0 is normal)."""
        self._settings.extra["speed"] = speed
