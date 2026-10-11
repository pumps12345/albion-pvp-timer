"""Offline speech recognition with Vosk, gated by push-to-talk.

SpeechWorker lives on its own QThread. The sounddevice callback (PortAudio's thread) only
queues audio while push-to-talk is held. The worker feeds that audio to Vosk every 50 ms
and emits the final text shortly after the key is released.
"""
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .abilities import RESERVED_WORD, normalize_phrase
from .router import UNKNOWN_SPEECH

SAMPLE_RATE = 16000
BLOCK_SIZE = 800          # 50 ms of audio per callback
FEED_INTERVAL_MS = 50
PTT_TAIL_MS = 150         # keep recording briefly after release so the last syllable isn't cut off
REOPEN_INTERVAL_S = 10.0  # always-listen mode: how often to retry a microphone that stopped
log = logging.getLogger(__name__)


def build_grammar(phrases: Iterable[str], is_known: Callable[[str], bool]) -> list[str]:
    """Vosk grammar: every fully recognizable phrase, 'clear <phrase>', 'clear all', '[unk]'.
    Phrases containing unknown words are left out (Vosk would silently drop those words)."""
    usable = sorted({p for p in phrases if p and all(is_known(w) for w in p.split())})
    return [*usable, *(f"{RESERVED_WORD} {p}" for p in usable), f"{RESERVED_WORD} all", "[unk]"]


def extract_text(result_json: str) -> str:
    try:
        text = json.loads(result_json).get("text", "")
    except ValueError:
        return ""
    return normalize_phrase(" ".join(w for w in text.split() if w != UNKNOWN_SPEECH))


def result_text(result_json: str) -> str:
    """The recognized phrase; UNKNOWN_SPEECH if only speech outside the phrase list was heard;
    "" for silence."""
    text = extract_text(result_json)
    if text:
        return text
    try:
        raw = json.loads(result_json).get("text", "")
    except ValueError:
        return ""
    return UNKNOWN_SPEECH if UNKNOWN_SPEECH in raw.split() else ""


Usable = Callable[[int], bool]


def _any_device(index: int) -> bool:
    return True


def can_record(index: int) -> bool:
    """True if device `index` accepts the 16 kHz mono int16 stream Vosk needs. Windows lists
    each mic under several audio APIs, and some of them (WDM-KS, WASAPI) reject that format."""
    import sounddevice as sd
    try:
        sd.check_input_settings(device=index, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        return True
    except Exception:
        return False


def resolve_input_device(name: str | None, devices: list[dict], usable: Usable = _any_device) -> int | None:
    """Index of the first usable input device with exactly this name, else None (system default).
    Windows lists one microphone once per audio API, so names repeat; the first usable one wins."""
    if name is None:
        return None
    for index, device in enumerate(devices):
        if device["name"] == name and device["max_input_channels"] > 0 and usable(index):
            return index
    return None


def input_device_names(devices: list[dict], usable: Usable = _any_device) -> list[str]:
    names: list[str] = []
    for index, device in enumerate(devices):
        if device["max_input_channels"] > 0 and device["name"] not in names and usable(index):
            names.append(device["name"])
    return names


class SpeechWorker(QObject):
    recognized = Signal(str)
    model_ready = Signal()
    error = Signal(str)

    def __init__(self, model_path: Path, mic_device: str | None, always_listen: bool = False) -> None:
        super().__init__()
        self._model_path = model_path
        self._mic_device = mic_device
        self._always_listen = always_listen  # listen continuously instead of while push-to-talk is held
        self._last_reopen = 0.0
        self._model = None
        self._recognizer = None
        self._phrases: list[str] = []
        self._reported = False  # a callout was already emitted during this hold
        self._heard_unknown = False  # speech outside the phrase list was heard during this hold
        self._stream = None
        self._audio: queue.Queue[bytes] = queue.Queue()
        self._listening = threading.Event()
        self._known: dict[str, bool] = {}
        self._known_lock = threading.Lock()
        self._feed_timer: QTimer | None = None
        self._finalize_timer: QTimer | None = None

    # vocabulary (also called from the main thread by the editor) --------
    def is_known(self, word: str) -> bool:
        """True if the model can recognize `word`. Always True before the model loads."""
        if self._model is None:
            return True
        with self._known_lock:
            if word not in self._known:
                self._known[word] = self._model.vosk_model_find_word(word) != -1
            return self._known[word]

    def unknown_words(self, phrases: Iterable[str]) -> set[str]:
        return {w for p in phrases for w in p.split() if not self.is_known(w)}

    # lifecycle (worker thread) ------------------------------------------
    @Slot()
    def start(self) -> None:
        """Connected to QThread.started, so it runs on the worker thread."""
        self._create_timers()
        import vosk
        vosk.SetLogLevel(-1)
        if not self._model_path.exists():
            self.error.emit(f"Speech model not found at {self._model_path}. "
                            "Run scripts/get_model.py; speech is disabled.")
            return
        try:
            self._model = vosk.Model(str(self._model_path))
        except Exception as exc:
            self.error.emit(f"Could not load the speech model ({exc}); speech is disabled.")
            return
        self._rebuild_recognizer()
        self._open_stream()
        self._apply_listen_mode()
        self.model_ready.emit()

    def _create_timers(self) -> None:
        # Created on the worker thread (from start()) so they fire there.
        self._feed_timer = QTimer(self)
        self._feed_timer.setInterval(FEED_INTERVAL_MS)
        self._feed_timer.timeout.connect(self._feed)
        self._finalize_timer = QTimer(self)
        self._finalize_timer.setSingleShot(True)
        self._finalize_timer.setInterval(PTT_TAIL_MS)
        self._finalize_timer.timeout.connect(self._finalize)

    def stop(self) -> None:
        """Call from the main thread after the worker thread has finished."""
        self._listening.clear()
        self._close_stream()

    @Slot(list)
    def set_phrases(self, phrases: list) -> None:
        self._phrases = [str(p) for p in phrases]
        self._rebuild_recognizer()

    @Slot(bool)
    def set_always_listen(self, enabled: bool) -> None:
        self._always_listen = enabled
        self._apply_listen_mode()

    def _apply_listen_mode(self) -> None:
        """Switch between continuous listening and push-to-talk. Runs on the worker thread."""
        if self._recognizer is None:  # no model yet; start() applies the mode once it is loaded
            return
        self._finalize_timer.stop()
        self._drain(feed=False)
        self._recognizer.Reset()
        self._reported = False
        self._heard_unknown = False
        if self._always_listen:
            self._listening.set()
            self._feed_timer.start()
        else:
            self._listening.clear()
            self._feed_timer.stop()

    @Slot(object)
    def set_mic_device(self, name: str | None) -> None:
        self._mic_device = name
        if self._model is not None:
            self._open_stream()

    def _rebuild_recognizer(self) -> None:
        if self._model is None:
            return
        import vosk
        grammar = build_grammar(self._phrases, self.is_known)
        self._recognizer = vosk.KaldiRecognizer(self._model, SAMPLE_RATE, json.dumps(grammar))

    # audio --------------------------------------------------------------
    def _open_stream(self) -> None:
        import sounddevice as sd
        self._close_stream()
        index = resolve_input_device(self._mic_device, list(sd.query_devices()), can_record)
        if self._mic_device is not None and index is None:
            self.error.emit(f"Microphone '{self._mic_device}' not found; using the system default.")
        for device in ([index, None] if index is not None else [None]):
            try:
                self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                                                 dtype="int16", channels=1, device=device,
                                                 callback=self._on_audio)
                self._stream.start()
                if device != index:
                    self.error.emit(f"Microphone '{self._mic_device}' could not be opened; "
                                    "using the system default.")
                return
            except Exception as exc:
                log.warning("could not open input device %r: %s", device, exc)
                self._stream = None
        self.error.emit("No microphone could be opened; speech is disabled.")

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def _on_audio(self, indata, frames, time_info, status) -> None:
        # PortAudio thread: do nothing but queue audio while push-to-talk is held.
        if self._listening.is_set():
            self._audio.put(bytes(indata))

    # push-to-talk (worker thread, via queued signals) ---------------------
    @Slot()
    def on_ptt_down(self) -> None:
        if self._recognizer is None or self._always_listen:
            return
        if self._finalize_timer.isActive():  # pressed again during the tail: finish the last one
            self._finalize_timer.stop()
            self._finalize()
        if self._stream is None or not self._stream.active:
            # The mic stopped (e.g. headset unplugged or default device changed): reopen it.
            log.warning("microphone stream inactive; reopening")
            self._open_stream()
        self._drain(feed=False)
        self._recognizer.Reset()
        self._reported = False
        self._heard_unknown = False
        self._listening.set()
        self._feed_timer.start()

    @Slot()
    def on_ptt_up(self) -> None:
        if self._recognizer is None or self._always_listen or not self._listening.is_set():
            return
        self._finalize_timer.start()

    def _feed(self) -> None:
        if self._always_listen and (self._stream is None or not self._stream.active):
            # The mic stopped (e.g. headset unplugged): keep trying, but not on every 50 ms tick.
            now = time.monotonic()
            if now - self._last_reopen >= REOPEN_INTERVAL_S:
                self._last_reopen = now
                log.warning("microphone stream inactive; reopening")
                self._open_stream()
        self._drain(feed=True)

    def _drain(self, feed: bool) -> None:
        while True:
            try:
                chunk = self._audio.get_nowait()
            except queue.Empty:
                return
            if feed and self._recognizer.AcceptWaveform(chunk):
                # Vosk found a pause: that's one complete callout, report it right away.
                self._report(result_text(self._recognizer.Result()))

    def _report(self, text: str) -> None:
        if text == UNKNOWN_SPEECH:
            self._heard_unknown = True
            if self._always_listen:  # no end-of-hold summary in this mode, so report it now
                self.recognized.emit(text)
        elif text:
            self._reported = True
            self.recognized.emit(text)

    def _finalize(self) -> None:
        self._listening.clear()
        self._feed_timer.stop()
        self._drain(feed=True)
        self._report(result_text(self._recognizer.FinalResult()))
        self._recognizer.Reset()
        if not self._reported:  # nothing matched during the whole hold
            self.recognized.emit(UNKNOWN_SPEECH if self._heard_unknown else "")
