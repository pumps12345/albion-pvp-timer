"""The taskbar window: a header bar of app actions, a warning banner, and the ability editor."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QVBoxLayout, QWidget)

BANNER_STYLE = ("QFrame#banner { background: #fef3c7; border: 1px solid #f59e0b; border-radius: 4px; }"
                "QFrame#banner QLabel { color: #78350f; }")


class MainWindow(QMainWindow):
    move_overlay_toggled = Signal(bool)
    settings_requested = Signal()
    test_timer_requested = Signal()
    quit_requested = Signal()

    def __init__(self, editor: QWidget, icon: QIcon) -> None:
        super().__init__()
        self.setWindowTitle("PVPTimer")
        self.setWindowIcon(icon)
        self.resize(820, 700)
        self._warnings: list[str] = []

        self.move_button = QPushButton("⇕ Move overlay")
        self.move_button.setCheckable(True)
        self.move_button.setToolTip("Drag the timers where you want them, then click again to lock them")
        self.settings_button = QPushButton("⚙ Settings")
        self.test_timer_button = QPushButton("▶ Test timer")
        self.test_timer_button.setToolTip("Show an 8-second sample timer on the overlay")
        self.quit_button = QPushButton("Quit")
        header = QHBoxLayout()
        for button in (self.move_button, self.settings_button, self.test_timer_button):
            header.addWidget(button)
        header.addStretch(1)
        header.addWidget(self.quit_button)

        self.banner = QFrame(objectName="banner")
        self.banner.setStyleSheet(BANNER_STYLE)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        self.banner_close_button = QPushButton("✕")
        self.banner_close_button.setFlat(True)
        self.banner_close_button.setFixedWidth(28)
        self.banner_close_button.setToolTip("Dismiss")
        banner_row = QHBoxLayout(self.banner)
        banner_row.addWidget(self.banner_label, 1)
        banner_row.addWidget(self.banner_close_button, 0, Qt.AlignmentFlag.AlignTop)
        self.banner.hide()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(header)
        layout.addWidget(self.banner)
        layout.addWidget(editor, 1)
        self.setCentralWidget(central)

        self.move_button.toggled.connect(self.move_overlay_toggled)
        self.settings_button.clicked.connect(self.settings_requested)
        self.test_timer_button.clicked.connect(self.test_timer_requested)
        self.quit_button.clicked.connect(self.quit_requested)
        self.banner_close_button.clicked.connect(self._dismiss_warnings)

    def show_warning(self, message: str) -> None:
        """Add a message to the banner and flash the taskbar button if the window isn't active."""
        if message not in self._warnings:
            self._warnings.append(message)
        self.banner_label.setText("\n".join(self._warnings))
        self.banner.show()
        QApplication.alert(self)

    def clear_warning(self, message: str) -> None:
        """Remove a message that no longer applies; hide the banner when none are left."""
        if message in self._warnings:
            self._warnings.remove(message)
            self.banner_label.setText("\n".join(self._warnings))
            self.banner.setVisible(bool(self._warnings))

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _dismiss_warnings(self) -> None:
        self._warnings.clear()
        self.banner.hide()

    def closeEvent(self, event) -> None:
        # Closing the window quits the app; minimizing keeps the overlay and voice running.
        self.quit_requested.emit()
        event.accept()
