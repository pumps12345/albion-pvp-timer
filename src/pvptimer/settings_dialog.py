"""Settings dialog. Returns an edited copy of Settings; the app applies and saves it."""
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QPushButton, QSlider)

from .hotkey import PttListener
from .settings import PttBinding, Settings

NOT_SET = "Not set – click, then press your key"


def _spin(minimum: float, maximum: float, step: float, value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(1)
    spin.setSuffix(" s")
    spin.setValue(value)
    return spin


def _slider(minimum: int, maximum: int, value: int) -> QSlider:
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setValue(value)
    return slider


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, input_devices: list[str], ptt: PttListener | None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PVPTimer – Settings")
        self._base = settings
        self._binding = settings.ptt
        self._ptt = ptt

        self.ptt_button = QPushButton(self._binding_text())
        self.ptt_button.setEnabled(ptt is not None)
        self.ptt_button.clicked.connect(self._start_capture)

        self.mic_combo = QComboBox()
        self.mic_combo.addItem("System default", None)
        for name in input_devices:
            self.mic_combo.addItem(name, name)
        if settings.mic_device is not None:
            index = self.mic_combo.findData(settings.mic_device)
            if index < 0:
                self.mic_combo.addItem(f"{settings.mic_device} (not connected)", settings.mic_device)
                index = self.mic_combo.count() - 1
            self.mic_combo.setCurrentIndex(index)

        self.offset_spin = _spin(0.0, 3.0, 0.1, settings.speech_offset_s)
        self.offset_spin.setToolTip("Time between the enemy casting and you finishing the phrase. "
                                    "Subtracted from every timer.")
        self.warning_spin = _spin(0.0, 30.0, 0.5, settings.warning_s)
        self.ready_spin = _spin(0.5, 15.0, 0.5, settings.ready_display_s)
        self.beep_check = QCheckBox("Beep when an ability is ready")
        self.beep_check.setChecked(settings.beep_enabled)
        self.volume_slider = _slider(0, 100, round(settings.beep_volume * 100))
        self.opacity_slider = _slider(20, 100, round(settings.overlay.opacity * 100))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(self._binding is not None)

        form = QFormLayout(self)
        form.addRow("Push-to-talk", self.ptt_button)
        form.addRow("Microphone", self.mic_combo)
        form.addRow("Speech delay", self.offset_spin)
        form.addRow("Warning before ready", self.warning_spin)
        form.addRow("Show READY for", self.ready_spin)
        form.addRow("", self.beep_check)
        form.addRow("Beep volume", self.volume_slider)
        form.addRow("Overlay opacity", self.opacity_slider)
        form.addRow(buttons)

        if ptt is not None:
            ptt.captured.connect(self._on_captured)
            ptt.capture_cancelled.connect(self._on_capture_cancelled)

    def result_settings(self) -> Settings:
        return replace(
            self._base,
            ptt=self._binding,
            mic_device=self.mic_combo.currentData(),
            speech_offset_s=self.offset_spin.value(),
            warning_s=self.warning_spin.value(),
            ready_display_s=self.ready_spin.value(),
            beep_enabled=self.beep_check.isChecked(),
            beep_volume=self.volume_slider.value() / 100,
            overlay=replace(self._base.overlay, opacity=self.opacity_slider.value() / 100),
        )

    def done(self, result: int) -> None:
        if self._ptt is not None:
            self._ptt.cancel_capture()
            self._ptt.captured.disconnect(self._on_captured)
            self._ptt.capture_cancelled.disconnect(self._on_capture_cancelled)
            self._ptt = None
        super().done(result)

    def _binding_text(self) -> str:
        return self._binding.label() if self._binding else NOT_SET

    def _start_capture(self) -> None:
        self.ptt_button.setText("Press a key or mouse side button… (Esc cancels)")
        self._ptt.capture_next()

    def _on_captured(self, binding: PttBinding) -> None:
        self._binding = binding
        self.ptt_button.setText(self._binding_text())
        self.ok_button.setEnabled(True)

    def _on_capture_cancelled(self) -> None:
        self.ptt_button.setText(self._binding_text())
