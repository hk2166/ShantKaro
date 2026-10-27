import pytest

from shant.voice.formatter import SentenceBuffer, for_speech


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        ("अरे Rahul जी, मेरा refund कहाँ है?", "अरे Rahul जी, मेरा refund कहाँ है?"),
        ("*sighs* Fine, give me the number.", "Fine, give me the number."),
        ("(angrily) This is ridiculous!", "This is ridiculous!"),
        ("[pause] Okay.", "Okay."),
        ("This is **not** okay.", "This is not okay."),
        ("- first\n- second", "first second"),
        ("1. one\n2) two", "one two"),
        ("Thanks 🙏 guru 😤", "Thanks guru"),
        ("₹14,999 twice, SBD7712!", "₹14,999 twice, SBD7712!"),
        ("நீங்க `wrong` order அனுப்பிட்டீங்க", "நீங்க wrong order அனுப்பிட்டீங்க"),
        ("  too   many\n\nspaces ", "too many spaces"),
        ('"என்ன check பண்றீங்க? ஒரு மணி நேரம்தான்!"', "என்ன check பண்றீங்க? ஒரு மணி நேரம்தான்!"),
        ("“Finally, a human.”", "Finally, a human."),
        ('He said "wait" again.', 'He said "wait" again.'),
    ],
)
def test_for_speech(raw: str, spoken: str) -> None:
    assert for_speech(raw) == spoken


def test_sentences_come_out_as_soon_as_they_are_complete() -> None:
    buffer = SentenceBuffer()
    assert buffer.feed("अरे! तीन ") == ["अरे!"]
    assert buffer.feed("हफ्ते हो गए। पैसा") == ["तीन हफ्ते हो गए।"]
    assert buffer.feed(" कब आएगा?") == ["पैसा कब आएगा?"]
    assert buffer.flush() == []


def test_closing_quotes_stay_with_their_sentence() -> None:
    assert SentenceBuffer().feed('He said "today!" Then') == ['He said "today!"']


def test_flush_returns_a_reply_that_ends_without_a_full_stop() -> None:
    buffer = SentenceBuffer()
    assert buffer.feed("Fix it, guru") == []
    assert buffer.flush() == ["Fix it, guru"]
    assert buffer.flush() == []
