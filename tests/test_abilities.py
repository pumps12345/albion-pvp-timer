import pytest

from pvptimer.abilities import (ability_file, make_id, merge, normalize_phrase,
                                parse_ability_file, phrase_owners, validate)


@pytest.mark.parametrize("raw, expected", [
    ("  Blood-Letter  E! ", "blood letter e"),
    ("CLERIC ROBE R", "cleric robe r"),
    ("", ""),
    ("don't stop", "don't stop"),
])
def test_normalize_phrase(raw, expected):
    assert normalize_phrase(raw) == expected


def test_make_id_slugifies_and_avoids_collisions():
    assert make_id("Bloodletter E", []) == "bloodletter_e"
    assert make_id("Bloodletter E", ["bloodletter_e"]) == "bloodletter_e_2"
    assert make_id("Bloodletter E", ["bloodletter_e", "bloodletter_e_2"]) == "bloodletter_e_3"
    assert make_id("!!!", []) == "ability"


def test_normalized_cleans_name_and_phrases(make_ability):
    a = make_ability(name="  Bloodletter E ", phrases=("Blood Letter E", "  ", "blood E"))
    n = a.normalized()
    assert n.name == "Bloodletter E"
    assert n.phrases == ("blood letter e", "blood e")


def test_valid_ability_has_no_errors(make_ability):
    assert validate(make_ability(), []) == []


@pytest.mark.parametrize("changes, message", [
    ({"name": "  "}, "Name is required."),
    ({"slot": "X"}, "Slot must be one of: Q, W, E, R, D, F, Passive."),
    ({"cooldown_s": 0}, "Cooldown must be greater than 0 and at most 600 seconds."),
    ({"cooldown_s": 601}, "Cooldown must be greater than 0 and at most 600 seconds."),
    ({"phrases": ()}, "At least one phrase is required."),
    ({"phrases": ("!!",)}, "At least one phrase is required."),
    ({"phrases": ("clear blood",)}, "Phrase 'clear blood' starts with the reserved word 'clear'."),
    ({"phrases": ("blood e", "Blood E")}, "Phrase 'blood e' is listed twice."),
])
def test_validation_errors(make_ability, changes, message):
    assert message in validate(make_ability(**changes), [])


def test_phrase_used_by_another_ability_is_rejected(make_ability):
    other = make_ability(id="other", name="Cleric Robe R", slot="R", phrases=("robe r", "blood e"))
    assert validate(make_ability(phrases=("blood e",)), [other]) == [
        "Phrase 'blood e' is already used by Cleric Robe R."
    ]


def test_validation_ignores_the_abilitys_own_saved_copy(make_ability):
    assert validate(make_ability(cooldown_s=20.0), [make_ability()]) == []


def test_merge_user_overrides_defaults_and_appends_user_only(make_ability):
    d1 = make_ability(id="a", name="A", phrases=("a",))
    d2 = make_ability(id="b", name="B", phrases=("b",))
    u_b = make_ability(id="b", name="B custom", phrases=("bee",))
    u_c = make_ability(id="c", name="C", phrases=("c",))
    assert merge([d1, d2], [u_b, u_c], []) == [d1, u_b, u_c]


def test_merge_drops_deleted_ids(make_ability):
    d1 = make_ability(id="a", name="A", phrases=("a",))
    d2 = make_ability(id="b", name="B", phrases=("b",))
    assert merge([d1, d2], [], ["a"]) == [d2]


def test_phrase_owners_lists_every_owner(make_ability):
    a = make_ability(id="a", phrases=("x", "y"))
    b = make_ability(id="b", phrases=("y",))
    assert phrase_owners([a, b]) == {"x": [a], "y": [a, b]}


def test_ability_file_round_trip(make_ability):
    abilities = [make_ability(), make_ability(id="x", name="X", phrases=("x ray",))]
    assert parse_ability_file(ability_file(abilities, ["gone"])) == (abilities, ["gone"])


def test_parse_rejects_wrong_version():
    with pytest.raises(ValueError):
        parse_ability_file({"version": 99, "abilities": []})


def test_parse_rejects_malformed_entry():
    with pytest.raises((KeyError, TypeError, ValueError)):
        parse_ability_file({"version": 1, "abilities": [{"id": "x"}]})
