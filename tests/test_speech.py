from pathlib import Path
from types import SimpleNamespace

import pytest

from pvptimer import paths
from pvptimer.speech import (SpeechWorker, build_grammar, extract_text, input_device_names,
                             resolve_input_device)

needs_model = pytest.mark.skipif(not paths.model_dir().exists(), reason="Vosk model not downloaded")


def test_build_grammar_skips_phrases_with_unknown_words_and_adds_commands():
    grammar = build_grammar(["robe r", "hellion d", "blood e", "robe r", ""], lambda w: w != "hellion")
    assert grammar == ["blood e", "robe r", "clear blood e", "clear robe r", "clear all", "[unk]"]


def test_build_grammar_with_no_phrases_still_has_commands():
    assert build_grammar([], lambda w: True) == ["clear all", "[unk]"]


@pytest.mark.parametrize("raw, text", [
    ('{"text": "blood letter e"}', "blood letter e"),
    ('{"text": "[unk] blood e"}', "blood e"),
    ('{"text": "[unk]"}', ""),
    ('{"text": ""}', ""),
    ("{}", ""),
    ("not json", ""),
])
def test_extract_text(raw, text):
    assert extract_text(raw) == text


DEVICES = [
    {"name": "Speakers", "max_input_channels": 0},
    {"name": "Headset Mic", "max_input_channels": 1},   # MME
    {"name": "Desk Mic", "max_input_channels": 2},
    {"name": "Headset Mic", "max_input_channels": 1},   # same mic again under WASAPI
]


def test_resolve_input_device_picks_first_exact_input_match():
    assert resolve_input_device("Headset Mic", DEVICES) == 1
    assert resolve_input_device("Speakers", DEVICES) is None   # output-only
    assert resolve_input_device("Unplugged Mic", DEVICES) is None
    assert resolve_input_device(None, DEVICES) is None


def test_input_device_names_are_unique_inputs_in_order():
    assert input_device_names(DEVICES) == ["Headset Mic", "Desk Mic"]


def test_unknown_words_uses_model_lookup():
    worker = SpeechWorker(Path("unused"), None)
    assert worker.unknown_words(["hellion d"]) == set()  # before the model loads: assume known
    worker._model = SimpleNamespace(vosk_model_find_word=lambda w: -1 if w == "hellion" else 7)
    assert worker.unknown_words(["hellion d", "blood e"]) == {"hellion"}


@needs_model
def test_real_model_vocabulary_lookup():
    import vosk
    vosk.SetLogLevel(-1)
    model = vosk.Model(str(paths.model_dir()))
    assert model.vosk_model_find_word("blood") != -1
    assert model.vosk_model_find_word("qzxv") == -1


class FakeRecognizer:
    """Stands in for KaldiRecognizer. A chunk equal to b"PAUSE" makes Vosk report an endpoint."""

    def __init__(self, segments, final):
        self._segments = list(segments)
        self._final = final
        self.fed = []

    def AcceptWaveform(self, chunk):
        self.fed.append(chunk)
        return chunk == b"PAUSE"

    def Result(self):
        return f'{{"text": "{self._segments.pop(0)}"}}'

    def FinalResult(self):
        return f'{{"text": "{self._final}"}}'

    def Reset(self):
        pass


class FakeStream:
    def __init__(self, active=True):
        self.active = active

    def close(self):
        self.active = False


@pytest.fixture
def worker(qtbot):
    w = SpeechWorker(Path("unused"), None)
    w._create_timers()
    w._stream = FakeStream()
    heard = []
    w.recognized.connect(heard.append)
    return w, heard


def hold(w, *chunks):
    w.on_ptt_down()
    for chunk in chunks:
        w._audio.put(chunk)
    w.on_ptt_up()
    w._finalize_timer.stop()
    w._finalize()


def test_each_callout_in_one_hold_is_reported_separately(worker):
    w, heard = worker
    w._recognizer = FakeRecognizer(["blood letter e"], "robe r")
    hold(w, b"a", b"PAUSE", b"b")
    assert heard == ["blood letter e", "robe r"]


def test_hold_without_speech_reports_heard_nothing_once(worker):
    w, heard = worker
    w._recognizer = FakeRecognizer([], "[unk]")
    hold(w, b"noise")
    assert heard == [""]


def test_audio_before_the_press_is_discarded(worker):
    w, heard = worker
    w._recognizer = FakeRecognizer([], "blood e")
    w._audio.put(b"stale")
    hold(w, b"fresh")
    assert w._recognizer.fed == [b"fresh"]


def test_dead_microphone_stream_is_reopened_on_press(worker, monkeypatch):
    w, _ = worker
    w._recognizer = FakeRecognizer([], "")
    w._stream = FakeStream(active=False)  # e.g. USB headset unplugged and plugged back in
    reopened = []
    monkeypatch.setattr(w, "_open_stream", lambda: reopened.append(True))
    w.on_ptt_down()
    assert reopened == [True]


def test_device_list_and_lookup_skip_devices_that_cannot_record():
    usable = lambda index: index != 1  # e.g. a WDM-KS entry that rejects 16 kHz mono
    assert input_device_names(DEVICES, usable) == ["Desk Mic", "Headset Mic"]
    assert resolve_input_device("Headset Mic", DEVICES, usable) == 3


def test_chosen_mic_that_fails_to_open_falls_back_with_a_warning(qtbot, monkeypatch):
    import sounddevice as sd

    class Stream:
        active = True

        def __init__(self, device, **kwargs):
            if device is not None:
                raise OSError("Invalid sample rate")
            self.device = device

        def start(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(sd, "query_devices", lambda: DEVICES)
    monkeypatch.setattr(sd, "check_input_settings", lambda **kwargs: None)
    monkeypatch.setattr(sd, "RawInputStream", Stream)
    w = SpeechWorker(Path("unused"), "Desk Mic")
    errors = []
    w.error.connect(errors.append)
    w._open_stream()
    assert w._stream.device is None
    assert errors == ["Microphone 'Desk Mic' could not be opened; using the system default."]
