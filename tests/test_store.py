import json

import pytest

from pvptimer.abilities import ability_file
from pvptimer.store import AbilityStore


@pytest.fixture
def files(tmp_path, make_ability):
    defaults = tmp_path / "defaults.json"
    user = tmp_path / "user" / "abilities.json"
    defaults.write_text(json.dumps(ability_file([
        make_ability(id="bloodletter_e", name="Bloodletter E", phrases=("blood letter e", "blood e")),
        make_ability(id="cleric_robe_r", name="Cleric Robe R", slot="R", cooldown_s=30.0,
                     phrases=("cleric robe r",)),
    ])), encoding="utf-8")
    return defaults, user


def new_store(files):
    store = AbilityStore(*files)
    store.load()
    return store


def test_load_defaults_without_user_file(files):
    store = new_store(files)
    assert [a.name for a in store.abilities()] == ["Bloodletter E", "Cleric Robe R"]
    assert store.warnings == []


def test_match_normalizes_text(files):
    store = new_store(files)
    assert store.match("Blood-Letter E!").id == "bloodletter_e"
    assert store.match("nothing") is None


def test_upsert_new_ability_assigns_id_persists_and_emits(files, make_ability):
    store = new_store(files)
    seen = []
    store.abilities_changed.connect(lambda: seen.append(True))
    stored = store.upsert(make_ability(id="", name="Hellion Hood D", slot="D", cooldown_s=25.0,
                                       phrases=("Hell Ion D",)))
    assert stored.id == "hellion_hood_d"
    assert stored.phrases == ("hell ion d",)
    assert seen == [True]
    assert new_store(files).match("hell ion d").id == "hellion_hood_d"


def test_upsert_invalid_raises_and_changes_nothing(files, make_ability):
    store = new_store(files)
    with pytest.raises(ValueError, match="already used by Bloodletter E"):
        store.upsert(make_ability(id="", name="Copy", phrases=("blood e",)))
    assert len(store.abilities()) == 2
    assert not files[1].exists()


def test_editing_a_default_writes_an_override_only(files, make_ability):
    defaults_before = files[0].read_text(encoding="utf-8")
    store = new_store(files)
    store.upsert(make_ability(id="cleric_robe_r", name="Cleric Robe R", slot="R", cooldown_s=25.0,
                              phrases=("robe r",)))
    assert files[0].read_text(encoding="utf-8") == defaults_before
    reloaded = new_store(files)
    assert reloaded.get("cleric_robe_r").cooldown_s == 25.0
    assert reloaded.match("cleric robe r") is None


def test_deleting_a_default_hides_it_after_reload(files):
    new_store(files).delete("cleric_robe_r")
    assert new_store(files).get("cleric_robe_r") is None


def test_deleting_a_user_ability_removes_it(files, make_ability):
    store = new_store(files)
    store.upsert(make_ability(id="", name="Mine", phrases=("mine",)))
    store.delete("mine")
    assert new_store(files).get("mine") is None


def test_delete_many_removes_defaults_and_user_abilities_with_one_notification(files, make_ability, qtbot):
    store = new_store(files)
    store.upsert(make_ability(id="", name="Mine", phrases=("mine",)))
    with qtbot.waitSignal(store.abilities_changed, timeout=1000):
        store.delete_many(["bloodletter_e", "cleric_robe_r", "mine", "not_a_real_id"])
    assert store.abilities() == []
    reloaded = new_store(files)
    assert reloaded.abilities() == []  # deleted defaults stay deleted after a restart


def test_delete_many_with_nothing_does_nothing(files):
    store = new_store(files)
    store.delete_many([])
    assert len(store.abilities()) == 2
    assert not files[1].exists()  # no save happened


def test_new_ability_never_reuses_a_deleted_default_id(files, make_ability):
    store = new_store(files)
    store.delete("cleric_robe_r")
    stored = store.upsert(make_ability(id="", name="Cleric Robe R", slot="R", phrases=("robe r",)))
    assert stored.id == "cleric_robe_r_2"


def test_corrupt_user_file_is_quarantined_and_defaults_load(files):
    files[1].parent.mkdir(parents=True)
    files[1].write_text("{broken", encoding="utf-8")
    store = new_store(files)
    assert len(store.abilities()) == 2
    assert len(store.warnings) == 1
    assert list(files[1].parent.glob("abilities.json.bad-*"))


def test_duplicate_phrase_between_default_and_user_is_reported_and_first_owner_wins(files, make_ability):
    # A user phrase that a newer defaults file also uses.
    files[1].parent.mkdir(parents=True)
    files[1].write_text(json.dumps(ability_file([make_ability(id="mine", name="Mine", phrases=("blood e",))])),
                        encoding="utf-8")
    store = new_store(files)
    assert store.duplicate_phrases() == {"blood e"}
    assert store.match("blood e").id == "bloodletter_e"


def test_export_then_import_into_fresh_store(files, tmp_path, make_ability):
    store = new_store(files)
    store.upsert(make_ability(id="", name="Mine", phrases=("mine",)))
    export = tmp_path / "export.json"
    store.export_file(export)
    empty_defaults = tmp_path / "empty_defaults.json"
    empty_defaults.write_text(json.dumps(ability_file([])), encoding="utf-8")
    other = AbilityStore(empty_defaults, tmp_path / "other" / "abilities.json")
    other.load()
    result = other.import_file(export, replace_existing=lambda old, new: True)
    assert sorted(result.added) == ["Bloodletter E", "Cleric Robe R", "Mine"]
    assert other.match("mine").id == "mine"


def test_import_conflicts_ask_and_respect_answer(files, tmp_path, make_ability):
    incoming = tmp_path / "in.json"
    incoming.write_text(json.dumps(ability_file([
        make_ability(id="bloodletter_e", name="Bloodletter E", cooldown_s=99.0, phrases=("blood letter e",))
    ])), encoding="utf-8")
    store = new_store(files)
    kept = store.import_file(incoming, replace_existing=lambda old, new: False)
    assert kept.kept == ["Bloodletter E"]
    assert store.get("bloodletter_e").cooldown_s == 15.0
    replaced = store.import_file(incoming, replace_existing=lambda old, new: True)
    assert replaced.replaced == ["Bloodletter E"]
    assert store.get("bloodletter_e").cooldown_s == 99.0


def test_import_skips_invalid_entries(files, tmp_path, make_ability):
    incoming = tmp_path / "in.json"
    incoming.write_text(json.dumps(ability_file([make_ability(id="copy", name="Copy", phrases=("blood e",))])),
                        encoding="utf-8")
    store = new_store(files)
    result = store.import_file(incoming, replace_existing=lambda old, new: True)
    assert result.skipped == ["Copy: Phrase 'blood e' is already used by Bloodletter E."]
    assert store.get("copy") is None


def test_import_rejects_non_ability_file(files, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        new_store(files).import_file(bad, replace_existing=lambda old, new: True)
