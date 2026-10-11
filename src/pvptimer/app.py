"""Application wiring (skeleton: tray, overlay, timers, debug timer). Replaced in Task 13."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from types import SimpleNamespace

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import paths
from .beep import ReadyBeep
from .overlay import OverlayWindow
from .settings import load_settings, save_settings
from .timers import TimerManager

TICK_MS = 66  # ~15 fps
DEBUG_ABILITY = SimpleNamespace(id="debug_test", name="Test timer", cooldown_s=8.0)
log = logging.getLogger("pvptimer")


def make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(245, 158, 11))
    p.setPen(QPen(QColor(15, 23, 42), 4))
    p.drawEllipse(6, 6, 52, 52)
    p.drawLine(32, 32, 32, 14)
    p.drawLine(32, 32, 45, 38)
    p.end()
    return QIcon(pix)


class PvpTimerApp(QObject):
    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self._qapp = qapp
        home = paths.app_data_dir()
        self._settings_path = home / "settings.json"
        self.settings, settings_warning = load_settings(self._settings_path)
        s = self.settings

        self.timers = TimerManager(speech_offset_s=s.speech_offset_s, warning_s=s.warning_s,
                                   ready_display_s=s.ready_display_s)
        self.overlay = OverlayWindow(self.timers, s.overlay)
        self.overlay.position_changed.connect(self._save_overlay_position)
        self.beep = ReadyBeep(paths.data_dir() / "ready.wav", s.beep_volume, s.beep_enabled)

        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip("PVPTimer")
        self.tray.setContextMenu(self._build_menu())
        self.tray.show()

        self._tick = QTimer(self)
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.overlay.show()
        if settings_warning:
            self._notify(settings_warning)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        self._move_action = QAction("Move overlay", menu, checkable=True)
        self._move_action.toggled.connect(self.overlay.set_move_mode)
        menu.addAction(self._move_action)
        menu.addSeparator()
        menu.addAction("Debug: fire test timer", lambda: self.timers.start(DEBUG_ABILITY))
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._menu = menu
        return menu

    def _on_tick(self) -> None:
        if self.timers.ready_events():
            self.beep.play()
        self.overlay.update()

    def _notify(self, message: str) -> None:
        log.warning(message)
        self.tray.showMessage("PVPTimer", message, QSystemTrayIcon.MessageIcon.Warning, 6000)

    def _save_overlay_position(self, screen: int, x: int, y: int) -> None:
        overlay = self.settings.overlay
        overlay.screen, overlay.x, overlay.y = screen, x, y
        save_settings(self._settings_path, self.settings)

    def shutdown(self) -> None:
        self._tick.stop()
        self.overlay.close()
        self.tray.hide()

    def quit(self) -> None:
        self.shutdown()
        self._qapp.quit()


def setup_logging() -> None:
    handler = RotatingFileHandler(paths.app_data_dir() / "pvptimer.log", maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    sys.excepthook = lambda *exc: log.critical("unhandled exception", exc_info=exc)


def main() -> int:
    setup_logging()
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    app = PvpTimerApp(qapp)  # noqa: F841  (kept alive for the event loop)
    return qapp.exec()
