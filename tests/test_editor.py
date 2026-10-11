import json

import pytest
from PySide6.QtWidgets import QMessageBox

from pvptimer.abilities import ability_file
from pvptimer.editor import EditorWindow, ability_status, describe_test_result
from pvptimer.store import AbilityStore


def fake_unknown(phrases):
    return {w for p in phrases for w in p.split() if w == "hellion"}


@pytest.fixture
def store(tmp_path, make_ability):
    defaults = tmp_path / "defaults.json"
    defaults.write_text(json.dumps(ability_file([
        make_ability(phrases=("blood letter e", "blood e")),
        make_ability(id="hellion_hood_d", name="Hellion Hood D", slot="D", cooldown_s=25.0,
                     phrases=("hellion d",)),
    ])), encoding="utf-8")
    s = AbilityStore(defaults, tmp_path / "user.json")
    s.load()
    return s


@pytest.fixture
def editor(qtbot, store):
    window = EditorWindow(store, fake_unknown)
    qtbot.addWidget(window)
    return window


def column(editor, index):
    return [editor.table.item(r, index).text() for r in range(editor.table.rowCount())]


def test_ability_status(make_ability):
    assert ability_status(make_ability(phrases=("blood e", "hellion e")), fake_unknown, set())[0] == "⚠ word"
    b = make_ability(phrases=("blood e",))
    assert ability_status(b, fake_unknown, {"blood e"}) == ("⚠ dup", "Also used by another ability: blood e")
    assert ability_status(b, fake_unknown, set()) == ("✓", "")


def test_describe_test_result(make_ability):
    bl = make_ability()
    assert describe_test_result("", None, "bloodletter_e", False) == "Heard nothing — try again."
    assert describe_test_result("hello", None, "x", False) == 'Heard: "hello" → ✗ no match'
    assert describe_test_result("blood e", bl, "bloodletter_e", False) == 'Heard: "blood e" → ✓ matches Bloodletter E'
    assert describe_test_result("blood e", bl, "other", False) == \
        'Heard: "blood e" → matches a different ability: Bloodletter E'
    assert describe_test_result("blood e", bl, "bloodletter_e", True).endswith(
        "(unsaved changes can't be heard until you Save)")


def test_table_lists_abilities_with_status(editor):
    assert column(editor, 0) == ["Bloodletter E", "Hellion Hood D"]
    assert column(editor, 3) == ["blood letter e, blood e", "hellion d"]
    assert column(editor, 4) == ["✓", "⚠ word"]
    assert "hellion" in editor.table.item(1, 4).toolTip()


def test_new_ability_form_validates_then_saves(editor, store):
    editor.add_button.click()
    assert not editor.save_button.isEnabled()
    editor.name_edit.setText("Cleric Robe R")
    editor.slot_combo.setCurrentText("R")
    editor.cooldown_spin.setValue(30.0)
    editor.phrases_edit.setPlainText("blood e")
    assert "already used by Bloodletter E" in editor.errors_label.text()
    assert not editor.save_button.isEnabled()
    editor.phrases_edit.setPlainText("cleric robe r\nrobe r")
    assert editor.errors_label.text() == ""
    assert editor.save_button.isEnabled()
    editor.save_button.click()
    saved = store.get("cleric_robe_r")
    assert saved.phrases == ("cleric robe r", "robe r") and saved.cooldown_s == 30.0
    assert "Cleric Robe R" in column(editor, 0)
    assert not editor.save_button.isEnabled()  # saved form is no longer dirty


def add(editor, name, phrases):
    editor.name_edit.setText(name)
    editor.phrases_edit.setPlainText(phrases)
    editor.save_button.click()


def test_saving_clears_the_form_for_the_next_ability(editor, store):
    editor.add_button.click()
    add(editor, "Cleric Robe R", "cleric robe r")
    assert editor.name_edit.text() == ""
    assert editor.phrases_edit.toPlainText() == ""
    assert editor.form_title.text() == "New ability (saved “Cleric Robe R”)"
    assert editor.table.selectionModel().selectedRows() == []
    add(editor, "Royal Cowl D", "royal cowl d")  # straight into the next one
    assert store.get("cleric_robe_r") is not None and store.get("royal_cowl_d") is not None


def test_saving_an_edit_also_clears_the_form(editor, store):
    editor.table.selectRow(0)
    editor.cooldown_spin.setValue(20.0)
    editor.save_button.click()
    assert store.get("bloodletter_e").cooldown_s == 20.0
    assert editor.name_edit.text() == ""
    assert editor.form_title.text() == "New ability (saved “Bloodletter E”)"


def test_selecting_a_row_loads_it_and_revert_discards_edits(editor):
    editor.table.selectRow(0)
    assert editor.name_edit.text() == "Bloodletter E"
    assert not editor.save_button.isEnabled()
    editor.cooldown_spin.setValue(20.0)
    assert editor.save_button.isEnabled()
    editor.revert_button.click()
    assert editor.cooldown_spin.value() == 15.0


def test_search_hides_non_matching_rows(editor):
    editor.search_edit.setText("hell")
    assert [editor.table.isRowHidden(r) for r in range(2)] == [True, False]
    editor.search_edit.setText("blood e")  # phrases are searched too
    assert [editor.table.isRowHidden(r) for r in range(2)] == [False, True]


def test_delete_asks_then_removes(editor, store, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    editor.table.selectRow(1)
    editor.delete_button.click()
    assert store.get("hellion_hood_d") is None
    assert column(editor, 0) == ["Bloodletter E"]


def test_test_result_is_shown_only_while_waiting(qtbot, editor, store):
    editor.table.selectRow(0)
    editor.show_test_result("blood e", store.get("bloodletter_e"))
    assert editor.test_label.text() == ""  # not waiting: ignored
    with qtbot.waitSignal(editor.test_requested):
        editor.test_button.click()
    editor.show_test_result("blood e", store.get("bloodletter_e"))
    assert editor.test_label.text() == 'Heard: "blood e" → ✓ matches Bloodletter E'


def test_describe_test_result_for_unknown_speech():
    assert describe_test_result("[unk]", None, "x", False) ==         "Heard speech, but it isn't one of your saved phrases."


@pytest.fixture
def categorized(qtbot, tmp_path, make_ability):
    defaults = tmp_path / "cat_defaults.json"
    defaults.write_text(json.dumps(ability_file([
        make_ability(category="weapon"),
        make_ability(id="hh_ret", name="Hunter Hood – Retaliate D", slot="D", cooldown_s=45.0,
                     phrases=("hunter hood retaliate",), category="armor_item"),
        make_ability(id="ret_d", name="Retaliate D", slot="D", cooldown_s=45.0,
                     phrases=("retaliate d", "retaliate"), category="armor_ability"),
    ])), encoding="utf-8")
    s = AbilityStore(defaults, tmp_path / "cat_user.json")
    s.load()
    window = EditorWindow(s, fake_unknown)
    qtbot.addWidget(window)
    return window, s


def tab_texts(editor):
    return [editor.tabs.tabText(i) for i in range(editor.tabs.count())]


def visible_names(editor):
    return [editor.table.item(r, 0).text() for r in range(editor.table.rowCount())
            if not editor.table.isRowHidden(r)]


def test_tabs_show_counts_per_category(categorized):
    editor, _ = categorized
    assert tab_texts(editor) == ["All 3", "Weapons 1", "Armor items 1", "Armor abilities 1", "Custom 0"]


def test_tabs_filter_the_list_together_with_search(categorized):
    editor, _ = categorized
    editor.tabs.setCurrentIndex(3)  # Armor abilities
    assert visible_names(editor) == ["Retaliate D"]
    editor.tabs.setCurrentIndex(0)  # All
    editor.search_edit.setText("retaliate")
    assert visible_names(editor) == ["Hunter Hood – Retaliate D", "Retaliate D"]
    editor.tabs.setCurrentIndex(2)  # Armor items + search
    assert visible_names(editor) == ["Hunter Hood – Retaliate D"]


def test_new_ability_saved_on_another_tab_shows_up_under_custom(categorized):
    editor, store = categorized
    editor.tabs.setCurrentIndex(1)  # Weapons
    editor.add_button.click()
    add(editor, "Purge Spell", "purge spell")
    assert store.get("purge_spell").category == "custom"
    assert editor.tabs.currentIndex() == 4
    assert visible_names(editor) == ["Purge Spell"]
    assert tab_texts(editor)[4] == "Custom 1"


def test_editing_a_built_in_keeps_its_category(categorized):
    editor, store = categorized
    editor.tabs.setCurrentIndex(3)
    editor.table.selectRow(2)  # rows are sorted by name: Bloodletter E, Hunter Hood…, Retaliate D
    assert editor.name_edit.text() == "Retaliate D"
    editor.cooldown_spin.setValue(40.0)
    editor.save_button.click()
    assert store.get("ret_d").category == "armor_ability"
    assert store.get("ret_d").cooldown_s == 40.0
