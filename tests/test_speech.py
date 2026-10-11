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
