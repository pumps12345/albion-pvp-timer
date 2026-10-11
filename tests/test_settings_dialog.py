from pvptimer.settings import OverlaySettings, PttBinding, Settings
from pvptimer.settings_dialog import SettingsDialog


def test_dialog_shows_current_values_and_returns_edits(qtbot):
    s = Settings(ptt=PttBinding("mouse", "x1"), mic_device="Headset")
    dlg = SettingsDialog(s, ["Desk Mic", "Headset"], ptt=None)
    qtbot.addWidget(dlg)
    assert dlg.ptt_button.text() == "Mouse X1"
    assert dlg.mic_combo.currentText() == "Headset"
    assert dlg.offset_spin.value() == 0.7

    dlg.offset_spin.setValue(1.2)
    dlg.warning_spin.setValue(5.0)
    dlg.ready_spin.setValue(2.0)
    dlg.beep_check.setChecked(False)
    dlg.volume_slider.setValue(30)
    dlg.opacity_slider.setValue(50)
    dlg.mic_combo.setCurrentIndex(0)  # System default
    assert dlg.result_settings() == Settings(
        ptt=PttBinding("mouse", "x1"), mic_device=None, speech_offset_s=1.2, warning_s=5.0,
        ready_display_s=2.0, beep_enabled=False, beep_volume=0.3,
        overlay=OverlaySettings(0, 40, 200, 0.5),
    )


def test_ok_requires_a_push_to_talk_binding(qtbot):
    dlg = SettingsDialog(Settings(), [], ptt=None)
    qtbot.addWidget(dlg)
    assert not dlg.ok_button.isEnabled()
    dlg._on_captured(PttBinding("keyboard", "f8"))
    assert dlg.ok_button.isEnabled()
    assert dlg.ptt_button.text() == "Key F8"
    assert dlg.result_settings().ptt == PttBinding("keyboard", "f8")


def test_missing_microphone_is_kept_and_labelled(qtbot):
    dlg = SettingsDialog(Settings(mic_device="Old USB Mic"), ["Desk Mic"], ptt=None)
    qtbot.addWidget(dlg)
    assert dlg.mic_combo.currentText() == "Old USB Mic (not connected)"
    assert dlg.result_settings().mic_device == "Old USB Mic"


def test_appearance_controls_show_current_values(qtbot):
    dlg = SettingsDialog(Settings(overlay=OverlaySettings(bar_width=300, bar_height=30)), [], ptt=None)
    qtbot.addWidget(dlg)
    assert dlg.width_slider.value() == 300
    assert dlg.height_slider.value() == 30
    assert dlg.color_buttons["running"].text() == "#64748b"


def test_appearance_edits_update_preview_and_result(qtbot):
    dlg = SettingsDialog(Settings(), [], ptt=None)
    qtbot.addWidget(dlg)
    dlg.width_slider.setValue(400)
    dlg.height_slider.setValue(40)
    dlg.set_color("ready", "#0000ff")
    assert dlg.preview.style.bar_width == 400
    assert dlg.preview.style.color_ready == "#0000ff"
    overlay = dlg.result_settings().overlay
    assert (overlay.bar_width, overlay.bar_height, overlay.color_ready) == (400, 40, "#0000ff")
    assert dlg.color_buttons["ready"].text() == "#0000ff"


def test_reset_appearance_restores_defaults_but_keeps_opacity(qtbot):
    dlg = SettingsDialog(Settings(), [], ptt=None)
    qtbot.addWidget(dlg)
    dlg.width_slider.setValue(500)
    dlg.set_color("running", "#ff0000")
    dlg.opacity_slider.setValue(50)
    dlg.reset_appearance_button.click()
    assert dlg.result_settings().overlay == OverlaySettings(opacity=0.5)
