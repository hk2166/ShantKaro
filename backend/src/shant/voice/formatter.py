"""Clean the customer's text before it's spoken.

Gnani's TTS already reads numbers, ₹ amounts and IDs aloud correctly (its Text Normalization
Guide), so this only removes things a voice shouldn't say: markdown, stage directions, emoji.
"""

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_STAGE_DIRECTION = re.compile(r"\*[^*\n]+\*|\([^)\n]*\)|\[[^\]\n]*\]")
_LIST_MARKER = re.compile(r"^\s*(?:[-•]|\d+[.)])\s+", re.MULTILINE)
_MARKUP = re.compile(r"[*_`#]")
_OPEN_QUOTES = "\"'“‘"
_CLOSE_QUOTES = "\"'”’"
_EMOJI = re.compile("[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\ufe0f\u200d]")
# A sentence ends at . ! ? or the Devanagari danda, plus any closing quotes after it.
_SENTENCE_END = re.compile(r"[.!?।]+[\"'”’]*")


def for_speech(text: str) -> str:
    text = _BOLD.sub(r"\1", text)
    text = _STAGE_DIRECTION.sub(" ", text)
    text = _LIST_MARKER.sub("", text)
    text = _MARKUP.sub("", text)
    text = _EMOJI.sub("", text)
    text = " ".join(text.split())
    if len(text) > 1 and text[0] in _OPEN_QUOTES and text[-1] in _CLOSE_QUOTES:
        text = text[1:-1].strip()
    return text


class SentenceBuffer:
    """Collects streamed text and hands back each sentence as soon as it is complete.

    The voice starts speaking on the first full sentence instead of waiting for the whole
    reply (task.md §5.2).
    """

    def __init__(self) -> None:
        self._text = ""

    def feed(self, chunk: str) -> list[str]:
        self._text += chunk
        sentences = []
        while match := _SENTENCE_END.search(self._text):
            sentences.append(self._text[: match.end()].strip())
            self._text = self._text[match.end() :]
        return [sentence for sentence in sentences if sentence]

    def flush(self) -> list[str]:
        """Return whatever is left when the reply ends without a full stop."""
        rest, self._text = self._text.strip(), ""
        return [rest] if rest else []
