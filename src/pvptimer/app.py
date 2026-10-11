"""Application wiring: main window, overlay, timers, push-to-talk, speech, editor and settings."""
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from types import SimpleNamespace

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from . import paths
from .beep import ReadyBeep
from .editor import EditorWindow
from .hotkey import PttListener
from .instance import InstanceServer, acquire_single_instance, ask_running_instance_to_show
from .main_window import MainWindow
from .overlay import OverlayWindow
from .router import Action, decide
from .settings import Settings, load_settings, save_settings
from .settings_dialog import SettingsDialog
from .speech import SpeechWorker, can_record, input_device_names
from .store import AbilityStore
from .timers import TimerManager

TICK_MS = 66  # ~15 fps
TEST_WINDOW_S = 10.0
DEBUG_ABILITY = SimpleNamespace(id="debug_test", name="Test timer", cooldown_s=8.0)
NO_ABILITIES = "No abilities saved yet. Use + Add below to add the enemy abilities you want to call out."
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
    phrases_changed = Signal(list)   # -> SpeechWorker.set_phrases (queued to the worker thread)
    mic_changed = Signal(object)     # -> SpeechWorker.set_mic_device

    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self._qapp = qapp
        home = paths.app_data_dir()
        self._settings_path = home / "settings.json"
        self.settings, settings_warning = load_settings(self._settings_path)
        s = self.settings

        self.store = AbilityStore(paths.data_dir() / "default_abilities.json", home / "abilities.json")
        self.store.load()

        self.timers = TimerManager(speech_offset_s=s.speech_offset_s, warning_s=s.warning_s,
                                   ready_display_s=s.ready_display_s)
        self.overlay = OverlayWindow(self.timers, s.overlay)
        self.overlay.position_changed.connect(self._save_overlay_position)
        self.beep = ReadyBeep(paths.data_dir() / "ready.wav", s.beep_volume, s.beep_enabled)

        self.ptt = PttListener()
        self.ptt.failed.connect(self._on_ptt_failed)

        self.speech = SpeechWorker(paths.model_dir(), s.mic_device)
        self._speech_thread = QThread()
        self.speech.moveToThread(self._speech_thread)
        self._speech_thread.started.connect(self.speech.start)
        self.ptt.ptt_down.connect(self.speech.on_ptt_down)
        self.ptt.ptt_up.connect(self.speech.on_ptt_up)
        self.phrases_changed.connect(self.speech.set_phrases)
        self.mic_changed.connect(self.speech.set_mic_device)
        self.speech.recognized.connect(self._on_recognized)
        self.speech.model_ready.connect(self._on_model_ready)
        self.speech.error.connect(self._notify)
        self.store.abilities_changed.connect(self._push_phrases)

        self._test_deadline = 0.0
        self._settings_open = False
        self._shut_down = False

        self.editor = EditorWindow(self.store, self.speech.unknown_words)
        self.editor.test_requested.connect(self._arm_test)
        self.main = MainWindow(self.editor, make_icon())
        self.main.move_overlay_toggled.connect(self.overlay.set_move_mode)
        self.main.settings_requested.connect(lambda: self.open_settings())
        self.main.test_timer_requested.connect(lambda: self.timers.start(DEBUG_ABILITY))
        self.main.quit_requested.connect(self.quit)
        self._instance = InstanceServer()
        self._instance.activated.connect(self.main.bring_to_front)
        self.store.abilities_changed.connect(self._on_abilities_changed)

        self._tick = QTimer(self)
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        self.overlay.show()
        self.main.show()
        self._push_phrases()
        self._speech_thread.start()
        self.ptt.start(s.ptt)

        for warning in [settings_warning, *self.store.warnings]:
            if warning:
                self._notify(warning)
        if not self.store.abilities():
            self._notify(NO_ABILITIES)
        if s.ptt is None:
            QTimer.singleShot(0, self.open_settings)  # first run: ask for the push-to-talk key

    # runtime ------------------------------------------------------------
    def _on_tick(self) -> None:
        if self.timers.ready_events():  # before overlay paints, which calls snapshot()
            self.beep.play()
        self.overlay.update()

    def _on_abilities_changed(self) -> None:
        if self.store.abilities():
            self.main.clear_warning(NO_ABILITIES)

    def _push_phrases(self) -> None:
        self.phrases_changed.emit(self.store.phrases())

    def _on_recognized(self, text: str) -> None:
        test_mode = time.monotonic() < self._test_deadline
        self._test_deadline = 0.0
        decision = decide(text, self.store.match, test_mode)
        log.info("heard %r -> %s", decision.text, decision.action.value)
        if decision.action is Action.TEST_RESULT:
            self.editor.show_test_result(decision.text, decision.ability)
        elif decision.action is Action.CLEAR_ALL:
            self.timers.clear_all()
        elif decision.action is Action.CLEAR:
            self.timers.clear(decision.ability.id)
        elif decision.action is Action.START:
            self.timers.start(decision.ability)
        else:
            self.overlay.show_heard(decision.text, bool(self.store.phrases()))

    def _on_model_ready(self) -> None:
        flagged = [a.name for a in self.store.abilities() if self.speech.unknown_words(a.phrases)]
        if flagged:
            self._notify(f"{len(flagged)} abilities have phrases with unrecognized words "
                         f"({', '.join(flagged[:5])}). Open the Editor to respell them.")
        self._push_phrases()  # rebuild the grammar now that the vocabulary is known
        self.editor.refresh()

    def _notify(self, message: str) -> None:
        log.warning(message)
        self.main.show_warning(message)

    def _on_ptt_failed(self, message: str) -> None:
        self._notify(message)
        self.open_settings()

    def _save_overlay_position(self, screen: int, x: int, y: int) -> None:
        overlay = self.settings.overlay
        overlay.screen, overlay.x, overlay.y = screen, x, y
        save_settings(self._settings_path, self.settings)

    # windows ------------------------------------------------------------
    def open_editor(self) -> None:
        self.main.bring_to_front()

    def _arm_test(self) -> None:
        self._test_deadline = time.monotonic() + TEST_WINDOW_S

    def open_settings(self) -> None:
        if self._settings_open:
            return
        self._settings_open = True
        try:
            import sounddevice as sd
            try:
                devices = input_device_names(list(sd.query_devices()), can_record)
            except Exception as exc:
                log.warning("could not list audio devices: %s", exc)
                devices = []
            dialog = SettingsDialog(self.settings, devices, self.ptt, parent=self.main)
            if dialog.exec():
                self._apply_settings(dialog.result_settings())
        finally:
            self._settings_open = False

    def _apply_settings(self, new: Settings) -> None:
        old, self.settings = self.settings, new
        save_settings(self._settings_path, new)
        self.timers.speech_offset_s = new.speech_offset_s
        self.timers.warning_s = new.warning_s
        self.timers.ready_display_s = new.ready_display_s
        self.beep.configure(new.beep_volume, new.beep_enabled)
        self.overlay.apply_settings(new.overlay)
        if new.ptt != old.ptt:
            self.ptt.start(new.ptt)
        if new.mic_device != old.mic_device:
            self.mic_changed.emit(new.mic_device)

    # shutdown -----------------------------------------------------------
    def shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        self._tick.stop()
        self._instance.close()
        self.ptt.cancel_capture()
        self.ptt.stop()
        self._speech_thread.quit()
        self._speech_thread.wait(2000)
        self.speech.stop()
        self.overlay.close()
        self.main.close()  # its closeEvent calls quit(), which is a no-op once shut down

    def quit(self) -> None:
        if self._shut_down:
            return
        self.shutdown()
        self._qapp.quit()


def set_windows_app_id() -> None:
    """Give the process its own taskbar identity so Windows shows PVPTimer's icon, not Python's."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PVPTimer.App")


def setup_logging() -> None:
    handler = RotatingFileHandler(paths.app_data_dir() / "pvptimer.log", maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    sys.excepthook = lambda *exc: log.critical("unhandled exception", exc_info=exc)


def main() -> int:
    set_windows_app_id()
    setup_logging()
    qapp = QApplication(sys.argv)
    qapp.setWindowIcon(make_icon())
    lock = acquire_single_instance(paths.app_data_dir())
    if lock is None:
        if not ask_running_instance_to_show():
            QMessageBox.information(None, "PVPTimer", "PVPTimer is already running. Check your taskbar.")
        return 0
    qapp.setQuitOnLastWindowClosed(False)  # the overlay is a window too; quitting is explicit
    app = PvpTimerApp(qapp)  # noqa: F841  (kept alive for the event loop)
    qapp.aboutToQuit.connect(lock.unlock)
    return qapp.exec()
