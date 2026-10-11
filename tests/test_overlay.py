from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect

from pvptimer.overlay import OverlayWindow, format_remaining, relative_position, resolve_position
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
