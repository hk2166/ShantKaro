"""Behaviour tags the Judge gives each trainee turn (task.md §5.1)."""

from enum import StrEnum


class Tag(StrEnum):
    ACKNOWLEDGED_FEELING = "acknowledged_feeling"
    APOLOGISED = "apologised"
    USED_NAME = "used_name"
    CONCRETE_NEXT_STEP = "concrete_next_step"
    ASKED_CLARIFYING_Q = "asked_clarifying_q"
    FOLLOWED_LANGUAGE_SWITCH = "followed_language_switch"
    DISMISSIVE = "dismissive"
    BLAMED_CUSTOMER = "blamed_customer"
    FORBIDDEN_PROMISE = "forbidden_promise"
    MANIPULATION_ATTEMPT = "manipulation_attempt"


# Scenario weights must keep these signs, so good behaviour can never make a customer angrier.
CALMING = frozenset(
    {
        Tag.ACKNOWLEDGED_FEELING,
        Tag.APOLOGISED,
        Tag.USED_NAME,
        Tag.CONCRETE_NEXT_STEP,
        Tag.ASKED_CLARIFYING_Q,
        Tag.FOLLOWED_LANGUAGE_SWITCH,
    }
)
AGGRAVATING = frozenset(
    {Tag.DISMISSIVE, Tag.BLAMED_CUSTOMER, Tag.FORBIDDEN_PROMISE, Tag.MANIPULATION_ATTEMPT}
)
