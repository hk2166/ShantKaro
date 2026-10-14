import pytest

from shant.voice.formatter import for_speech


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
