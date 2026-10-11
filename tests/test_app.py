import shutil
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication

from pvptimer import app as app_module
from pvptimer import paths
from pvptimer.settings import load_settings


@pytest.fixture(autouse=True)
def empty_builtin_list(tmp_path, monkeypatch):
    """App tests start from an empty built-in ability list, whatever the shipped one contains."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "default_abilities.json").write_text('{"version": 1, "abilities": []}', encoding="utf-8")
    shutil.copy(paths.data_dir() / "ready.wav", data / "ready.wav")
    monkeypatch.setattr(app_module.paths, "data_dir", lambda: data)


@pytest.fixture
def notes(monkeypatch):
    messages = []
    monkeypatch.setattr(app_module.PvpTimerApp, "_notify", lambda self, message: messages.append(message))
    return messages


@pytest.fixture
def running_app(qtbot, tmp_path, monkeypatch, make_ability, notes):
    monkeypatch.setattr(app_module.paths, "model_dir", lambda *a: tmp_path / "no-model")
    monkeypatch.setattr(app_module.PvpTimerApp, "open_settings", lambda self: None)
    application = app_module.PvpTimerApp(QApplication.instance())
    application.store.upsert(make_ability())
    yield application
    application.shutdown()


def test_missing_model_is_reported(running_app, notes, qtbot):
    qtbot.waitUntil(lambda: any("Speech model not found" in m for m in notes), timeout=3000)


def test_recognized_phrase_starts_and_clears_timers(running_app):
    running_app._on_recognized("blood letter e")
    assert [v.ability_id for v in running_app.timers.snapshot()] == ["bloodletter_e"]
    running_app._on_recognized("clear blood letter e")
    assert running_app.timers.snapshot() == []
    running_app._on_recognized("blood letter e")
    running_app._on_recognized("clear all")
    assert running_app.timers.snapshot() == []


def test_unmatched_phrase_is_shown_on_overlay(running_app, monkeypatch):
    heard = []
    monkeypatch.setattr(running_app.overlay, "show_heard", lambda text, has_abilities: heard.append((text, has_abilities)))
    running_app._on_recognized("hello")
    running_app._on_recognized("")
    running_app._on_recognized("[unk]")
    assert heard == [("hello", True), ("", True), ("[unk]", True)]


def test_first_run_without_abilities_points_to_the_editor(qtbot, tmp_path, monkeypatch, notes):
    monkeypatch.setattr(app_module.paths, "model_dir", lambda *a: tmp_path / "no-model")
    monkeypatch.setattr(app_module.PvpTimerApp, "open_settings", lambda self: None)
    application = app_module.PvpTimerApp(QApplication.instance())
    try:
        assert any("No abilities saved yet" in m for m in notes)
    finally:
        application.shutdown()


def test_armed_test_routes_next_result_to_editor_only(running_app, monkeypatch):
    running_app.open_editor()
    results = []
    monkeypatch.setattr(running_app.editor, "show_test_result",
                        lambda text, ability: results.append((text, ability.id)))
    running_app._arm_test()
    running_app._on_recognized("blood letter e")
    assert results == [("blood letter e", "bloodletter_e")]
    assert running_app.timers.snapshot() == []
    running_app._on_recognized("blood letter e")  # test window used up: back to normal
    assert len(running_app.timers.snapshot()) == 1


def test_applying_settings_updates_components_and_saves(running_app):
    running_app._apply_settings(replace(running_app.settings, speech_offset_s=1.5, warning_s=5.0))
    assert running_app.timers.speech_offset_s == 1.5
    assert running_app.timers.warning_s == 5.0
    saved, _ = load_settings(paths.app_data_dir() / "settings.json")
    assert saved.speech_offset_s == 1.5


def test_app_opens_a_taskbar_window_with_the_editor(running_app):
    assert running_app.main.isVisible()
    assert running_app.main.windowTitle() == "PVPTimer"
    assert running_app.main.centralWidget().isAncestorOf(running_app.editor)


def test_header_actions_are_wired(running_app, monkeypatch):
    opened = []
    monkeypatch.setattr(running_app, "open_settings", lambda: opened.append(True))
    running_app.main.settings_requested.emit()
    assert opened == [True]
    running_app.main.test_timer_requested.emit()
    assert [v.ability_id for v in running_app.timers.snapshot()] == ["debug_test"]
    running_app.main.move_button.click()
    assert running_app.overlay._move_mode is True
    running_app.main.move_button.click()
    assert running_app.overlay._move_mode is False


def test_warnings_go_to_the_window_banner(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module.paths, "model_dir", lambda *a: tmp_path / "no-model")
    monkeypatch.setattr(app_module.PvpTimerApp, "open_settings", lambda self: None)
    application = app_module.PvpTimerApp(QApplication.instance())
    try:
        assert application.main.banner.isVisible()
        assert "No abilities saved yet" in application.main.banner_label.text()             or "Speech model not found" in application.main.banner_label.text()
    finally:
        application.shutdown()


def test_no_abilities_hint_clears_once_an_ability_is_added(qtbot, tmp_path, monkeypatch, make_ability):
    monkeypatch.setattr(app_module.paths, "model_dir", lambda *a: tmp_path / "no-model")
    monkeypatch.setattr(app_module.PvpTimerApp, "open_settings", lambda self: None)
    application = app_module.PvpTimerApp(QApplication.instance())
    try:
        assert "No abilities saved yet" in application.main.banner_label.text()
        application.store.upsert(make_ability())
        assert "No abilities saved yet" not in application.main.banner_label.text()
    finally:
        application.shutdown()
