"""Global push-to-talk via pynput.

Listener callbacks run on pynput's own threads. Signals emitted there are queued by Qt
to receivers on other threads, so no UI code runs on a pynput thread. The listener only
observes keys; the game and Discord still receive them.
"""
import threading

from pynput import keyboard, mouse
from PySide6.QtCore import QObject, Signal

from .settings import MOUSE_BUTTONS, PttBinding


def key_to_name(key) -> str | None:
    if isinstance(key, keyboard.Key):
        return key.name
    if isinstance(key, keyboard.KeyCode):
        if key.char and key.char.isprintable():
            return key.char.lower()
        if key.vk is not None:
            return f"vk:{key.vk}"
    return None


def button_to_name(button) -> str | None:
    name = getattr(button, "name", None)
    return name if name in MOUSE_BUTTONS else None


class PttState:
    """Turns raw press/release events into a single down/up pair, ignoring auto-repeat."""

    def __init__(self, binding: PttBinding | None) -> None:
        self.binding = binding
        self.is_down = False

    def press(self, device: str, name: str | None) -> bool:
        if self._matches(device, name) and not self.is_down:
            self.is_down = True
            return True
        return False

    def release(self, device: str, name: str | None) -> bool:
        if self._matches(device, name) and self.is_down:
            self.is_down = False
            return True
        return False

    def _matches(self, device: str, name: str | None) -> bool:
        return (self.binding is not None and name is not None
                and (device, name) == (self.binding.device, self.binding.name))


class PttListener(QObject):
    ptt_down = Signal()
    ptt_up = Signal()
    captured = Signal(object)  # PttBinding
    capture_cancelled = Signal()
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._state = PttState(None)
        self._listener = None
        self._capture_listeners: list = []
        self._capture_lock = threading.Lock()

    def start(self, binding: PttBinding | None) -> None:
        """(Re)start watching `binding`. None stops watching."""
        self.stop()
        self._state = PttState(binding)
        if binding is None:
            return
        try:
            if binding.device == "keyboard":
                self._listener = keyboard.Listener(on_press=self._on_key_press,
                                                   on_release=self._on_key_release)
            else:
                self._listener = mouse.Listener(on_click=self._on_click)
            self._listener.start()
        except Exception as exc:  # pynput raises platform-specific errors
            self._listener = None
            self.failed.emit(f"Could not watch the push-to-talk key: {exc}")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._state.is_down = False

    def _on_key_press(self, key) -> None:
        if self._state.press("keyboard", key_to_name(key)):
            self.ptt_down.emit()

    def _on_key_release(self, key) -> None:
        if self._state.release("keyboard", key_to_name(key)):
            self.ptt_up.emit()

    def _on_click(self, x, y, button, pressed) -> None:
        name = button_to_name(button)
        if pressed and self._state.press("mouse", name):
            self.ptt_down.emit()
        elif not pressed and self._state.release("mouse", name):
            self.ptt_up.emit()

    # capture ------------------------------------------------------------
    def capture_next(self) -> None:
        """Record the next key or extra mouse button pressed anywhere. Esc cancels."""
        self.cancel_capture()

        def on_key(key):
            if key == keyboard.Key.esc:
                self._finish_capture(None)
                return False
            name = key_to_name(key)
            if name:
                self._finish_capture(PttBinding("keyboard", name))
                return False
            return None

        def on_click(x, y, button, pressed):
            name = button_to_name(button)
            if pressed and name:
                self._finish_capture(PttBinding("mouse", name))
                return False
            return None

        with self._capture_lock:
            self._capture_listeners = [keyboard.Listener(on_press=on_key), mouse.Listener(on_click=on_click)]
            for listener in self._capture_listeners:
                listener.start()

    def cancel_capture(self) -> None:
        with self._capture_lock:
            listeners, self._capture_listeners = self._capture_listeners, []
        for listener in listeners:
            listener.stop()

    def _finish_capture(self, binding: PttBinding | None) -> None:
        with self._capture_lock:
            if not self._capture_listeners:
                return  # the other listener already finished the capture
            listeners, self._capture_listeners = self._capture_listeners, []
        for listener in listeners:
            listener.stop()
        if binding is None:
            self.capture_cancelled.emit()
        else:
            self.captured.emit(binding)
