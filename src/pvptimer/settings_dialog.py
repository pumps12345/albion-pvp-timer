"""Settings dialog. Returns an edited copy of Settings; the app applies and saves it."""
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QVBoxLayout)

from .hotkey import PttListener
from .overlay import BarPreview, text_color_for
from .settings import BAR_HEIGHT_RANGE, BAR_WIDTH_RANGE, OverlaySettings, PttBinding, Settings

NOT_SET = "Not set – click, then press your key"
COLOR_KEYS = (("running", "Counting down"), ("warning", "Warning"), ("ready", "READY"))


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


def _with_label(slider: QSlider, label: QLabel) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(slider, 1)
    label.setMinimumWidth(48)
    row.addWidget(label)
    return row


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, input_devices: list[str], ptt: PttListener | None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PVPTimer – Settings")
        self._base = settings
        self._binding = settings.ptt
        self._ptt = ptt

        self.always_check = QCheckBox("Always listen (no push-to-talk key)")
        self.always_check.setChecked(settings.always_listen)
        self.always_check.setToolTip("The microphone is always on while PVPTimer runs, so nothing needs to be held. "
                                     "Ordinary talk containing a saved phrase will start a timer, "
                                     "so use phrases that are unlikely to come up in normal conversation.")
        self.always_check.toggled.connect(lambda *_: self._update_listen_mode())

        self.ptt_button = QPushButton(self._binding_text())
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

        # overlay appearance
        overlay = settings.overlay
        self._colors = {key: getattr(overlay, f"color_{key}") for key, _ in COLOR_KEYS}
        self.color_buttons: dict[str, QPushButton] = {}
        for key, label in COLOR_KEYS:
            button = QPushButton()
            button.setToolTip(f"Bar color while {label.lower()}")
            button.clicked.connect(lambda _=False, k=key, t=label: self._pick_color(k, t))
            self.color_buttons[key] = button
            self._show_color(key)
        self.width_slider = _slider(*BAR_WIDTH_RANGE, overlay.bar_width)
        self.height_slider = _slider(*BAR_HEIGHT_RANGE, overlay.bar_height)
        self.width_label = QLabel()
        self.height_label = QLabel()
        self.reset_appearance_button = QPushButton("Reset appearance")
        self.reset_appearance_button.clicked.connect(self._reset_appearance)
        self.preview = BarPreview(self._overlay_style())
        self.width_slider.valueChanged.connect(lambda *_: self._appearance_changed())
        self.height_slider.valueChanged.connect(lambda *_: self._appearance_changed())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

        form = QFormLayout()
        form.addRow("Listening", self.always_check)
        form.addRow("Push-to-talk", self.ptt_button)
        form.addRow("Microphone", self.mic_combo)
        form.addRow("Speech delay", self.offset_spin)
        form.addRow("Warning before ready", self.warning_spin)
        form.addRow("Show READY for", self.ready_spin)
        form.addRow("", self.beep_check)
        form.addRow("Beep volume", self.volume_slider)
        form.addRow("Overlay opacity", self.opacity_slider)

        appearance = QGroupBox("Overlay appearance")
        look = QFormLayout(appearance)
        for key, label in COLOR_KEYS:
            look.addRow(f"{label} color", self.color_buttons[key])
        look.addRow("Bar width", _with_label(self.width_slider, self.width_label))
        look.addRow("Bar height", _with_label(self.height_slider, self.height_label))
        look.addRow("Preview", self.preview)
        look.addRow("", self.reset_appearance_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(appearance)
        layout.addWidget(buttons)
        self._appearance_changed()
        self._update_listen_mode()

        if ptt is not None:
            ptt.captured.connect(self._on_captured)
            ptt.capture_cancelled.connect(self._on_capture_cancelled)

    def result_settings(self) -> Settings:
        return replace(
            self._base,
            ptt=self._binding,
            always_listen=self.always_check.isChecked(),
            mic_device=self.mic_combo.currentData(),
            speech_offset_s=self.offset_spin.value(),
            warning_s=self.warning_spin.value(),
            ready_display_s=self.ready_spin.value(),
            beep_enabled=self.beep_check.isChecked(),
            beep_volume=self.volume_slider.value() / 100,
            overlay=self._overlay_style(),
        )

    def set_color(self, key: str, color: str) -> None:
        self._colors[key] = color.lower()
        self._show_color(key)
        self._appearance_changed()

    def _overlay_style(self) -> OverlaySettings:
        return replace(
            self._base.overlay,
            opacity=self.opacity_slider.value() / 100,
            bar_width=self.width_slider.value(),
            bar_height=self.height_slider.value(),
            color_running=self._colors["running"],
            color_warning=self._colors["warning"],
            color_ready=self._colors["ready"],
        )

    def _appearance_changed(self) -> None:
        self.width_label.setText(f"{self.width_slider.value()} px")
        self.height_label.setText(f"{self.height_slider.value()} px")
        self.preview.set_style(self._overlay_style())

    def _show_color(self, key: str) -> None:
        color = QColor(self._colors[key])
        self.color_buttons[key].setText(self._colors[key])
        self.color_buttons[key].setStyleSheet(
            f"background-color: {color.name()}; color: {text_color_for(color).name()};")

    def _pick_color(self, key: str, label: str) -> None:
        color = QColorDialog.getColor(QColor(self._colors[key]), self, f"{label} bar color")
        if color.isValid():
            self.set_color(key, color.name())

    def _reset_appearance(self) -> None:
        defaults = OverlaySettings()
        self.width_slider.setValue(defaults.bar_width)
        self.height_slider.setValue(defaults.bar_height)
        for key, _ in COLOR_KEYS:
            self._colors[key] = getattr(defaults, f"color_{key}")
            self._show_color(key)
        self._appearance_changed()

    def done(self, result: int) -> None:
        if self._ptt is not None:
            self._ptt.cancel_capture()
            self._ptt.captured.disconnect(self._on_captured)
            self._ptt.capture_cancelled.disconnect(self._on_capture_cancelled)
            self._ptt = None
        super().done(result)

    def _update_listen_mode(self) -> None:
        """A push-to-talk key is only needed (and only editable) when not always listening."""
        always = self.always_check.isChecked()
        self.ptt_button.setEnabled(self._ptt is not None and not always)
        self.ok_button.setEnabled(always or self._binding is not None)

    def _binding_text(self) -> str:
        return self._binding.label() if self._binding else NOT_SET

    def _start_capture(self) -> None:
        self.ptt_button.setText("Press a key or mouse side button… (Esc cancels)")
        self._ptt.capture_next()

    def _on_captured(self, binding: PttBinding) -> None:
        self._binding = binding
        self.ptt_button.setText(self._binding_text())
        self._update_listen_mode()

    def _on_capture_cancelled(self) -> None:
        self.ptt_button.setText(self._binding_text())
