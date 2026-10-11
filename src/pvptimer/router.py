"""Decides what a recognized phrase means. A pure function so it is unit-testable."""
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .abilities import RESERVED_WORD, Ability, normalize_phrase


class Action(Enum):
    TEST_RESULT = "test_result"
    CLEAR_ALL = "clear_all"
    CLEAR = "clear"
    START = "start"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class Decision:
    action: Action
    text: str
    ability: Ability | None = None


def decide(text: str, match: Callable[[str], Ability | None], test_mode: bool) -> Decision:
    text = normalize_phrase(text)
    if test_mode:
        return Decision(Action.TEST_RESULT, text, match(text) if text else None)
    if not text:
        return Decision(Action.NO_MATCH, text)
    if text == f"{RESERVED_WORD} all":
        return Decision(Action.CLEAR_ALL, text)
    head, _, rest = text.partition(" ")
    if head == RESERVED_WORD and rest:
        target = match(rest)
        return Decision(Action.CLEAR, text, target) if target else Decision(Action.NO_MATCH, text)
    ability = match(text)
    return Decision(Action.START, text, ability) if ability else Decision(Action.NO_MATCH, text)
