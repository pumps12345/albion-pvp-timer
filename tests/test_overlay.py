from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor

from pvptimer.overlay import (MAX_ROWS, ROW_GAP, BarPreview, OverlayWindow, format_remaining,
                              heard_message, relative_position, resolve_position, text_color_for)
from pvptimer.settings import OverlaySettings
from pvptimer.timers import TimerManager

SCREENS = [QRect(0, 0, 1920, 1080), QRect(1920, 0, 2560, 1440)]


@pytest.mark.parametrize("remaining, text", [
    (0, "READY"), (-1.2, "READY"), (4.31, "4.3"), (9.94, "9.9"), (10.0, "10"), (14.2, "15"),
])
def test_format_remaining(remaining, text):
    assert format_remaining(remaining) == text


def test_resolve_position_on_saved_screen():
    assert resolve_position(SCREENS, 1, 100, 50) == QPoint(2020, 50)


def test_resolve_position_falls_back_when_screen_missing():
    assert resolve_position(SCREENS, 5, 100, 50) == QPoint(40, 200)


def test_resolve_position_falls_back_when_offscreen():
    assert resolve_position(SCREENS, 0, 5000, 50) == QPoint(40, 200)


def test_relative_position_finds_screen():
    assert relative_position(SCREENS, QPoint(2020, 50)) == (1, 100, 50)
    assert relative_position(SCREENS, QPoint(-500, -500)) == (0, -500, -500)


def test_overlay_paints_every_state_without_errors(qtbot):
    clock = SimpleNamespace(now=0.0)
    timers = TimerManager(clock=lambda: clock.now, speech_offset_s=0.0)
    for ability_id, cooldown in [("run", 30), ("warn", 2), ("ready", 0.001)]:
        timers.start(SimpleNamespace(id=ability_id, name=ability_id.title(), cooldown_s=cooldown))
    clock.now = 0.01
    window = OverlayWindow(timers, OverlaySettings())
    qtbot.addWidget(window)
    window.show_heard("")
    assert not window.grab().isNull()
    window.show_heard("hello there")
    window.set_move_mode(True)
    assert not window.grab().isNull()


@pytest.mark.parametrize("text, has_abilities, message", [
    ("", True, "? heard nothing"),
    ("hello", True, '? heard: "hello"'),
    ("[unk]", True, "? not a saved phrase"),
    ("[unk]", False, "? no abilities saved – open Editor"),
])
def test_heard_message(text, has_abilities, message):
    assert heard_message(text, has_abilities) == message


def test_text_is_dark_on_light_bars_and_light_on_dark_bars():
    assert text_color_for(QColor("#ffff00")).lightness() < 60
    assert text_color_for(QColor("#22c55e")).lightness() < 60
    assert text_color_for(QColor("#64748b")).lightness() > 200
    assert text_color_for(QColor("#1d4ed8")).lightness() > 200


def test_overlay_uses_configured_bar_size_and_colors(qtbot):
    timers = TimerManager(speech_offset_s=0.0)
    timers.start(SimpleNamespace(id="a", name="Bloodletter E", cooldown_s=15))
    window = OverlayWindow(timers, OverlaySettings())
    qtbot.addWidget(window)
    big = OverlaySettings(bar_width=400, bar_height=40, color_running="#ffff00")
    window.apply_settings(big)
    assert window.width() == 400
    assert window.height() == (40 + ROW_GAP) * (MAX_ROWS + 1)
    image = window.grab().toImage()
    assert image.pixelColor(395, 20).name() == "#ffff00"  # right end of a full bar


def test_preview_shows_three_states_and_follows_style(qtbot):
    preview = BarPreview(OverlaySettings())
    qtbot.addWidget(preview)
    assert not preview.grab().isNull()
    preview.set_style(OverlaySettings(bar_width=300, bar_height=30))
    assert preview.minimumWidth() == 300
    assert preview.minimumHeight() == 3 * (30 + ROW_GAP)
