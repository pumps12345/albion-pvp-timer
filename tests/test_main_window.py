import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel

from pvptimer.main_window import MainWindow


@pytest.fixture
def window(qtbot):
    w = MainWindow(QLabel("editor goes here"), QIcon())
    qtbot.addWidget(w)
    return w


def test_header_buttons_emit_their_actions(qtbot, window):
    with qtbot.waitSignal(window.settings_requested):
        window.settings_button.click()
    with qtbot.waitSignal(window.test_timer_requested):
        window.test_timer_button.click()
    with qtbot.waitSignal(window.quit_requested):
        window.quit_button.click()


def test_move_overlay_is_a_toggle(qtbot, window):
    with qtbot.waitSignal(window.move_overlay_toggled) as on:
        window.move_button.click()
    assert on.args == [True]
    with qtbot.waitSignal(window.move_overlay_toggled) as off:
        window.move_button.click()
    assert off.args == [False]


def test_closing_the_window_asks_the_app_to_quit(qtbot, window):
    window.show()
    with qtbot.waitSignal(window.quit_requested):
        window.close()


def test_warning_banner_shows_and_can_be_dismissed(window):
    window.show()
    assert not window.banner.isVisible()
    window.show_warning("Microphone 'X' could not be opened; using the system default.")
    assert window.banner.isVisible()
    assert window.banner_label.text() == "Microphone 'X' could not be opened; using the system default."
    window.banner_close_button.click()
    assert not window.banner.isVisible()


def test_clearing_the_last_warning_hides_the_banner(window):
    window.show()
    window.show_warning("first")
    window.show_warning("second")
    window.clear_warning("first")
    assert window.banner_label.text() == "second"
    window.clear_warning("second")
    assert not window.banner.isVisible()
