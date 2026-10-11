import pytest

from pvptimer.router import Action, decide


@pytest.fixture
def match(make_ability):
    table = {
        "blood letter e": make_ability(),
        "cleric robe r": make_ability(id="robe", name="Cleric Robe R", slot="R", phrases=("cleric robe r",)),
    }
    return table.get


def test_known_phrase_starts_timer(match):
    d = decide("Blood Letter E", match, test_mode=False)
    assert d.action is Action.START and d.ability.id == "bloodletter_e" and d.text == "blood letter e"


def test_unknown_phrase_is_no_match(match):
    d = decide("hello", match, False)
    assert d.action is Action.NO_MATCH and d.text == "hello" and d.ability is None


def test_empty_text_is_no_match(match):
    d = decide("", match, False)
    assert d.action is Action.NO_MATCH and d.text == ""


def test_clear_all(match):
    assert decide("clear all", match, False).action is Action.CLEAR_ALL


def test_clear_phrase(match):
    d = decide("clear cleric robe r", match, False)
    assert d.action is Action.CLEAR and d.ability.id == "robe"


@pytest.mark.parametrize("text", ["clear nothing", "clear"])
def test_clear_unknown_is_no_match(match, text):
    assert decide(text, match, False).action is Action.NO_MATCH


@pytest.mark.parametrize("text, ability_id", [
    ("blood letter e", "bloodletter_e"),
    ("clear all", None),
    ("", None),
])
def test_test_mode_reports_match_without_acting(match, text, ability_id):
    d = decide(text, match, test_mode=True)
    assert d.action is Action.TEST_RESULT
    assert (d.ability.id if d.ability else None) == ability_id


def test_unknown_speech_is_no_match_and_kept_as_marker(match):
    d = decide("[unk]", match, False)
    assert d.action is Action.NO_MATCH and d.text == "[unk]"
    assert decide("[unk]", match, True).action is Action.TEST_RESULT
