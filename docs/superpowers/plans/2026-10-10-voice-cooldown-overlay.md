# PVPTimer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows tray app that listens on push-to-talk, recognizes enemy-ability callouts offline with Vosk, and draws cooldown timers on a transparent, click-through overlay above Albion Online. Abilities are managed in an in-app editor.

**Architecture:** One PySide6 process. Pure-Python logic modules (`abilities`, `jsonio`, `timers`, `router`, `settings`) have no Qt widgets and are fully unit-tested. Qt modules (`store`, `overlay`, `hotkey`, `speech`, `settings_dialog`, `editor`) wrap them. `app.py` connects everything with signals. Vosk runs on its own `QThread`, pynput and PortAudio callbacks run on their own threads, and every UI change happens on the Qt main thread.

**Tech Stack:** Python 3.13, PySide6 (Widgets, Multimedia), vosk (`vosk-model-small-en-us-0.15`), sounddevice, pynput, pytest + pytest-qt, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-10-10-voice-cooldown-overlay-design.md`. Read it before starting any task.

## Global Constraints

- Windows 10/11 only. Python `>=3.13`. Interpreter for creating the venv: `$LOCALAPPDATA/Programs/Python/Python313/python.exe`. After that, always use `.venv/Scripts/python`.
- Runtime dependencies: only `PySide6`, `vosk`, `sounddevice`, `pynput` (plus the standard library). Dev dependencies: `pytest`, `pytest-qt`, `pyinstaller`. Do not add others (no numpy).
- The app never reads game memory, injects into the game process, or inspects network traffic.
- Vosk model: `vosk-model-small-en-us-0.15` in `models/` (gitignored), downloaded by `scripts/get_model.py`.
- User files live in `%APPDATA%\PVPTimer\` (`abilities.json`, `settings.json`, `pvptimer.log`). The env var `PVPTIMER_HOME` overrides that folder (tests always set it).
- Ability rules: slots `Q W E R D F Passive`. Cooldown `> 0` and `<= 600` s. At least one phrase. A phrase may not start with the reserved word `clear`. A phrase may belong to only one ability. Phrases are normalized (lowercase, punctuation → space, whitespace collapsed).
- File format versions: ability files and settings files both have `"version": 1`.
- Settings defaults: `ptt=None`, `mic_device=None`, `speech_offset_s=0.7`, `warning_s=3.0`, `ready_display_s=3.0`, `beep_enabled=true`, `beep_volume=0.6`, overlay `screen=0, x=40, y=200, opacity=0.9`.
- Overlay: redraw every 66 ms (~15 fps), rows 260 × 26 px, at most 12 rows, "heard" line shown for 1.5 s.
- Editor phrase test window: 10 s.
- Log: rotating, 1 MB × 3 files.
- JSON writes are atomic (write `*.tmp`, then `os.replace`). Unreadable files are renamed to `<name>.bad-<YYYYmmdd-HHMMSS>`.
- Every commit message ends with the trailer line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (pass it as a second `-m`).
- Commands below are for Git Bash, run from the repo root (the folder containing `pyproject.toml`).

## Review Focus

1. **One phrase owned by two abilities.** This can happen when a newer defaults file adds a phrase a user already has. Expected: matching is deterministic (the first owner in the effective list wins), and the editor marks the row `⚠ dup`. Tests: Task 4, Task 12.
2. **Push-to-talk tapped with no speech, or only noise.** Expected: empty text → overlay shows "? heard nothing", no crash and no timer. Tests: Task 7 (router), Task 8 (overlay paint), Task 10 (`extract_text`).
3. **Speech offset ≥ cooldown** (a tiny cooldown typed in the editor). Expected: the timer appears already READY, beeps once, and its bar never goes negative. Test: Task 5.
4. **Saved overlay position on a monitor that is no longer connected.** Expected: the overlay falls back to the primary screen at the default offset instead of opening off-screen. Test: Task 8.
5. **Saved microphone missing, or listed under several Windows audio APIs.** Expected: the first exact-name input device is used; if the name is missing, the system default is used and the user is warned. Test: Task 10.

---

## File Structure

```
PVPTimer/
  pyproject.toml                 # package metadata, deps, pytest config
  README.md                      # Task 14
  pvptimer.spec                  # Task 14, PyInstaller build
  scripts/get_model.py           # download + unpack a Vosk model into models/
  scripts/make_beep.py           # generates src/pvptimer/data/ready.wav
  spike/                         # Task 2 THROWAWAY recognition test
  src/pvptimer/
    __init__.py  __main__.py
    paths.py            # data/model/app-data locations (source and frozen)
    jsonio.py           # atomic JSON write, read-or-quarantine
    abilities.py        # Ability dataclass, normalize/validate/merge, file format (pure)
    store.py            # AbilityStore QObject: effective list, persistence, import/export
    timers.py           # TimerManager, TimerView, TimerState (pure)
    settings.py         # Settings dataclasses + load/save (pure)
    router.py           # decide(): what a recognized phrase means (pure)
    overlay.py          # OverlayWindow + format_remaining/resolve_position helpers
    beep.py             # ReadyBeep (QSoundEffect)
    hotkey.py           # PttListener (pynput) + PttState/key_to_name helpers
    speech.py           # SpeechWorker (Vosk + sounddevice) + grammar/device helpers
    settings_dialog.py  # SettingsDialog
    editor.py           # EditorWindow + ability_status/describe_test_result helpers
    app.py              # PvpTimerApp wiring, tray, logging, main()
    data/default_abilities.json  data/ready.wav
  tests/
    conftest.py  test_paths.py  test_jsonio.py  test_abilities.py  test_store.py
    test_timers.py  test_settings.py  test_router.py  test_overlay.py  test_hotkey.py
    test_speech.py  test_settings_dialog.py  test_editor.py  test_app.py
```

---

### Task 1: Project scaffold, paths, bundled data, model download

**Files:**
- Create: `pyproject.toml`, `src/pvptimer/__init__.py`, `src/pvptimer/paths.py`, `src/pvptimer/data/default_abilities.json`, `scripts/make_beep.py`, `scripts/get_model.py`, `tests/conftest.py`
- Generate: `src/pvptimer/data/ready.wav`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `paths.APP_NAME = "PVPTimer"`, `paths.MODEL_NAME = "vosk-model-small-en-us-0.15"`, `paths.data_dir() -> Path`, `paths.model_dir(name: str = MODEL_NAME) -> Path`, `paths.app_data_dir() -> Path`. Also the autouse test fixture `isolated_home` (sets `PVPTIMER_HOME`) in `tests/conftest.py`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "pvptimer"
version = "0.1.0"
description = "Voice-triggered enemy cooldown overlay for Albion Online"
requires-python = ">=3.13"
dependencies = [
    "PySide6>=6.8",
    "vosk>=0.3.45",
    "sounddevice>=0.5",
    "pynput>=1.7.7",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-qt>=4.4", "pyinstaller>=6.10"]

[project.gui-scripts]
pvptimer = "pvptimer.app:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
pvptimer = ["data/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
qt_api = "pyside6"
```

- [ ] **Step 2: Create the venv and install**

Run:
```bash
"$LOCALAPPDATA/Programs/Python/Python313/python.exe" -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
mkdir -p src/pvptimer/data && printf '__version__ = "0.1.0"\n' > src/pvptimer/__init__.py
.venv/Scripts/python -m pip install -e ".[dev]"
```
Expected: ends with `Successfully installed ... PySide6-... vosk-... sounddevice-... pynput-... pytest-qt-...`.

- [ ] **Step 3: Write `tests/conftest.py`**

```python
import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real %APPDATA%\\PVPTimer during tests."""
    home = tmp_path / "home"
    monkeypatch.setenv("PVPTIMER_HOME", str(home))
    return home
```

- [ ] **Step 4: Write the failing test `tests/test_paths.py`**

```python
from pvptimer import paths


def test_data_dir_contains_bundled_files():
    assert (paths.data_dir() / "default_abilities.json").is_file()
    assert (paths.data_dir() / "ready.wav").is_file()


def test_model_dir_is_under_repo_models_folder():
    model = paths.model_dir()
    assert model.name == paths.MODEL_NAME
    assert model.parent.name == "models"
    assert (model.parent.parent / "pyproject.toml").is_file()


def test_app_data_dir_uses_override_and_creates_it(tmp_path, monkeypatch):
    target = tmp_path / "custom"
    monkeypatch.setenv("PVPTIMER_HOME", str(target))
    assert paths.app_data_dir() == target
    assert target.is_dir()


def test_app_data_dir_defaults_to_appdata(tmp_path, monkeypatch):
    monkeypatch.delenv("PVPTIMER_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.app_data_dir() == tmp_path / "PVPTimer"
```

- [ ] **Step 5: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_paths.py -v`
Expected: FAIL with `ImportError: cannot import name 'paths'`.

- [ ] **Step 6: Implement `src/pvptimer/paths.py`**

```python
"""Filesystem locations, valid both from source and from the PyInstaller build."""
import os
import sys
from pathlib import Path

APP_NAME = "PVPTimer"
MODEL_NAME = "vosk-model-small-en-us-0.15"


def data_dir() -> Path:
    """Bundled read-only data (default abilities, sounds)."""
    return Path(__file__).resolve().parent / "data"


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def model_dir(name: str = MODEL_NAME) -> Path:
    return _bundle_root() / "models" / name


def app_data_dir() -> Path:
    """Per-user writable folder. PVPTIMER_HOME overrides it (used by tests)."""
    override = os.environ.get("PVPTIMER_HOME")
    if override:
        base = Path(override)
    else:
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base
```

- [ ] **Step 7: Create bundled data and scripts**

`src/pvptimer/data/default_abilities.json`:
```json
{
  "version": 1,
  "abilities": []
}
```

`scripts/make_beep.py`:
```python
"""Generate src/pvptimer/data/ready.wav: two short rising tones."""
import math
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parents[1] / "src" / "pvptimer" / "data" / "ready.wav"


def tone(freq: float, duration: float, volume: float = 0.5):
    n = int(RATE * duration)
    fade = int(RATE * 0.01)
    for i in range(n):
        envelope = min(1.0, i / fade, (n - i) / fade)
        yield volume * envelope * math.sin(2 * math.pi * freq * i / RATE)


def main() -> None:
    samples = [*tone(880, 0.09), *([0.0] * int(RATE * 0.04)), *tone(1320, 0.12)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
```

`scripts/get_model.py`:
```python
"""Download and unpack a Vosk model into ./models.

Usage: python scripts/get_model.py [model-name]
Default: vosk-model-small-en-us-0.15 (~40 MB).
Larger fallback (see spike): vosk-model-en-us-0.22-lgraph (~128 MB).
"""
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
BASE_URL = "https://alphacephei.com/vosk/models/"


def main(argv: list[str]) -> int:
    name = argv[1] if len(argv) > 1 else "vosk-model-small-en-us-0.15"
    target = MODELS / name
    if target.exists():
        print(f"{target} already exists")
        return 0
    MODELS.mkdir(exist_ok=True)
    archive = MODELS / f"{name}.zip"
    print(f"downloading {BASE_URL}{name}.zip ...")
    urllib.request.urlretrieve(f"{BASE_URL}{name}.zip", archive)
    with zipfile.ZipFile(archive) as zf:
        root = MODELS.resolve()
        for member in zf.namelist():
            if not (MODELS / member).resolve().is_relative_to(root):
                raise SystemExit(f"refusing unsafe path in archive: {member}")
        zf.extractall(MODELS)
    archive.unlink()
    print(f"model ready at {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

Run:
```bash
.venv/Scripts/python scripts/make_beep.py
.venv/Scripts/python scripts/get_model.py
```
Expected: `wrote ...ready.wav`, then `model ready at ...models/vosk-model-small-en-us-0.15`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_paths.py -v`
Expected: 4 passed.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src scripts tests
git commit -m "feat: project scaffold, paths, bundled data, model download script" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Recognition spike (THROWAWAY, needs the user)

This task answers the riskiest question in the spec (§11 step 0). **The executor cannot speak into the mic. Run the setup steps, then ask the user to run the script and paste its output.**

**Files:**
- Create: `spike/spike_recognize.py`, `spike/phrases.txt`, `spike/RESULTS.md`

**Interfaces:**
- Produces: a recorded decision in `spike/RESULTS.md`: which model to use, whether `Model.vosk_model_find_word` exists, and phrasing lessons. Task 10 depends on `vosk_model_find_word`.

- [ ] **Step 1: Write `spike/phrases.txt`**

```
# One phrase per line. Mix Albion names with slot letters. Edit freely.
blood letter e
bloodletter e
cleric robe r
hellion hood d
guardian helmet d
carving sword e
spirit hunter e
mercenary jacket r
assassin jacket r
judicator armor r
scholar robe r
royal cowl d
soldier boots f
```

- [ ] **Step 2: Write `spike/spike_recognize.py`**

```python
"""THROWAWAY spike: how well does Vosk + a grammar recognize Albion callouts on this mic?

Run:  .venv/Scripts/python spike/spike_recognize.py models/vosk-model-small-en-us-0.15 spike/phrases.txt
For each prompt: press Enter, then say the phrase. Recording lasts 2.5 s.
"""
import json
import sys
import time

import sounddevice as sd
import vosk

RATE = 16000
RECORD_S = 2.5
ROUNDS = 2


def recognize(rec: vosk.KaldiRecognizer, audio: bytes) -> str:
    parts = []
    if rec.AcceptWaveform(audio):
        parts.append(json.loads(rec.Result())["text"])
    parts.append(json.loads(rec.FinalResult())["text"])
    rec.Reset()
    return " ".join(p for p in parts if p).strip()


def main(model_path: str, phrases_path: str) -> None:
    vosk.SetLogLevel(-1)
    model = vosk.Model(model_path)
    print("Model.vosk_model_find_word available:", hasattr(model, "vosk_model_find_word"))
    with open(phrases_path, encoding="utf-8") as f:
        phrases = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]
    words = sorted({w for p in phrases for w in p.split()})
    unknown = [w for w in words if model.vosk_model_find_word(w) == -1]
    print("words NOT in vocabulary:", unknown or "none")
    usable = [p for p in phrases if not set(p.split()) & set(unknown)]
    print(f"{len(usable)}/{len(phrases)} phrases usable in the grammar\n")
    rec = vosk.KaldiRecognizer(model, RATE, json.dumps(usable + ["[unk]"]))

    results = []
    for round_no in range(1, ROUNDS + 1):
        for phrase in usable:
            input(f'[{round_no}/{ROUNDS}] Press Enter, then say: "{phrase}"')
            with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16") as stream:
                data, _ = stream.read(int(RECORD_S * RATE))
            t0 = time.perf_counter()
            heard = recognize(rec, bytes(data))
            ms = (time.perf_counter() - t0) * 1000
            ok = heard == phrase
            results.append((phrase, heard, ok, ms))
            print(f'   heard "{heard}"  {"OK" if ok else "MISS"}  ({ms:.0f} ms)')

    hits = sum(r[2] for r in results)
    print(f"\naccuracy: {hits}/{len(results)} = {hits / len(results):.0%}")
    print(f"recognition time: avg {sum(r[3] for r in results) / len(results):.0f} ms, "
          f"max {max(r[3] for r in results):.0f} ms")
    for phrase, heard, ok, _ in results:
        if not ok:
            print(f'   MISS "{phrase}" -> "{heard}"')


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

- [ ] **Step 3: HUMAN STEP: ask the user to run the spike**

Ask the user to run this in a terminal (it needs their voice):
```bash
.venv/Scripts/python spike/spike_recognize.py models/vosk-model-small-en-us-0.15 spike/phrases.txt
```
Ask them to paste the full output. If words are reported as missing from the vocabulary, help them respell those phrases in `spike/phrases.txt` using common words (e.g. `hellion` → `hell ion`), then run it again.

- [ ] **Step 4: Decide and record**

Write `spike/RESULTS.md` with: the pasted output(s), whether `vosk_model_find_word` exists, the final accuracy and latency, and respelling lessons.

Decision rule:
- If accuracy is ≥ 90% with the small model: keep `MODEL_NAME` as is.
- If it is below 90%: run `.venv/Scripts/python scripts/get_model.py vosk-model-en-us-0.22-lgraph` and repeat Step 3 with that model path. If lgraph reaches ≥ 90%, set `MODEL_NAME = "vosk-model-en-us-0.22-lgraph"` in `src/pvptimer/paths.py` and use that name for `MODEL` in Task 14. If neither model reaches 90%, stop and discuss with the user before continuing.
- If `vosk_model_find_word` is **not** available, stop and report back to the user. Task 10's `is_known` depends on it.

- [ ] **Step 5: Commit**

```bash
git add spike
git commit -m "spike: Vosk grammar recognition test and results (throwaway)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Ability model and JSON helpers (pure)

**Files:**
- Create: `src/pvptimer/jsonio.py`, `src/pvptimer/abilities.py`
- Modify: `tests/conftest.py` (add the `make_ability` fixture)
- Test: `tests/test_jsonio.py`, `tests/test_abilities.py`

**Interfaces:**
- Produces (`jsonio`): `atomic_write_json(path: Path, data: Any) -> None`; `load_or_quarantine(path: Path, parse: Callable[[Any], T]) -> tuple[T | None, str | None]`.
- Produces (`abilities`): `SLOTS`, `MAX_COOLDOWN_S = 600.0`, `RESERVED_WORD = "clear"`, `FORMAT_VERSION = 1`; `normalize_phrase(text: str) -> str`; `make_id(name: str, existing: Iterable[str]) -> str`; frozen dataclass `Ability(id: str, name: str, slot: str, cooldown_s: float, phrases: tuple[str, ...])` with `.normalized() -> Ability`, `.to_json() -> dict`, `Ability.from_json(dict) -> Ability`; `validate(ability: Ability, others: Iterable[Ability]) -> list[str]`; `merge(defaults, user, deleted_ids) -> list[Ability]`; `phrase_owners(abilities) -> dict[str, list[Ability]]`; `parse_ability_file(data) -> tuple[list[Ability], list[str]]`; `ability_file(abilities, deleted_ids=()) -> dict`.
- Produces (test fixture): `make_ability(id="bloodletter_e", name="Bloodletter E", slot="E", cooldown_s=15.0, phrases=("blood letter e",)) -> Ability`.

- [ ] **Step 1: Add the `make_ability` fixture to `tests/conftest.py`**

Append:
```python
from pvptimer.abilities import Ability


@pytest.fixture
def make_ability():
    def factory(id="bloodletter_e", name="Bloodletter E", slot="E", cooldown_s=15.0,
                phrases=("blood letter e",)):
        return Ability(id, name, slot, cooldown_s, tuple(phrases))
    return factory
```

- [ ] **Step 2: Write the failing tests**

`tests/test_jsonio.py`:
```python
import json

from pvptimer.jsonio import atomic_write_json, load_or_quarantine


def test_atomic_write_round_trips_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "sub" / "data.json"
    atomic_write_json(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert [p.name for p in path.parent.iterdir()] == ["data.json"]


def test_load_missing_file_returns_nothing(tmp_path):
    assert load_or_quarantine(tmp_path / "nope.json", dict) == (None, None)


def test_load_parses_with_given_function(tmp_path):
    path = tmp_path / "d.json"
    path.write_text('{"x": 2}', encoding="utf-8")
    assert load_or_quarantine(path, lambda d: d["x"]) == (2, None)


def test_unreadable_json_is_quarantined(tmp_path):
    path = tmp_path / "d.json"
    path.write_text("{not json", encoding="utf-8")
    value, warning = load_or_quarantine(path, dict)
    assert value is None
    assert "d.json" in warning
    assert not path.exists()
    assert len(list(tmp_path.glob("d.json.bad-*"))) == 1


def test_wrong_shape_is_quarantined(tmp_path):
    path = tmp_path / "d.json"
    path.write_text('{"y": 1}', encoding="utf-8")
    value, warning = load_or_quarantine(path, lambda d: d["x"])
    assert value is None and warning
```

`tests/test_abilities.py`:
```python
import pytest

from pvptimer.abilities import (ability_file, make_id, merge, normalize_phrase,
                                parse_ability_file, phrase_owners, validate)


@pytest.mark.parametrize("raw, expected", [
    ("  Blood-Letter  E! ", "blood letter e"),
    ("CLERIC ROBE R", "cleric robe r"),
    ("", ""),
    ("don't stop", "don't stop"),
])
def test_normalize_phrase(raw, expected):
    assert normalize_phrase(raw) == expected


def test_make_id_slugifies_and_avoids_collisions():
    assert make_id("Bloodletter E", []) == "bloodletter_e"
    assert make_id("Bloodletter E", ["bloodletter_e"]) == "bloodletter_e_2"
    assert make_id("Bloodletter E", ["bloodletter_e", "bloodletter_e_2"]) == "bloodletter_e_3"
    assert make_id("!!!", []) == "ability"


def test_normalized_cleans_name_and_phrases(make_ability):
    a = make_ability(name="  Bloodletter E ", phrases=("Blood Letter E", "  ", "blood E"))
    n = a.normalized()
    assert n.name == "Bloodletter E"
    assert n.phrases == ("blood letter e", "blood e")


def test_valid_ability_has_no_errors(make_ability):
    assert validate(make_ability(), []) == []


@pytest.mark.parametrize("changes, message", [
    ({"name": "  "}, "Name is required."),
    ({"slot": "X"}, "Slot must be one of: Q, W, E, R, D, F, Passive."),
    ({"cooldown_s": 0}, "Cooldown must be greater than 0 and at most 600 seconds."),
    ({"cooldown_s": 601}, "Cooldown must be greater than 0 and at most 600 seconds."),
    ({"phrases": ()}, "At least one phrase is required."),
    ({"phrases": ("!!",)}, "At least one phrase is required."),
    ({"phrases": ("clear blood",)}, "Phrase 'clear blood' starts with the reserved word 'clear'."),
    ({"phrases": ("blood e", "Blood E")}, "Phrase 'blood e' is listed twice."),
])
def test_validation_errors(make_ability, changes, message):
    assert message in validate(make_ability(**changes), [])


def test_phrase_used_by_another_ability_is_rejected(make_ability):
    other = make_ability(id="other", name="Cleric Robe R", slot="R", phrases=("robe r", "blood e"))
    assert validate(make_ability(phrases=("blood e",)), [other]) == [
        "Phrase 'blood e' is already used by Cleric Robe R."
    ]


def test_validation_ignores_the_abilitys_own_saved_copy(make_ability):
    assert validate(make_ability(cooldown_s=20.0), [make_ability()]) == []


def test_merge_user_overrides_defaults_and_appends_user_only(make_ability):
    d1 = make_ability(id="a", name="A", phrases=("a",))
    d2 = make_ability(id="b", name="B", phrases=("b",))
    u_b = make_ability(id="b", name="B custom", phrases=("bee",))
    u_c = make_ability(id="c", name="C", phrases=("c",))
    assert merge([d1, d2], [u_b, u_c], []) == [d1, u_b, u_c]


def test_merge_drops_deleted_ids(make_ability):
    d1 = make_ability(id="a", name="A", phrases=("a",))
    d2 = make_ability(id="b", name="B", phrases=("b",))
    assert merge([d1, d2], [], ["a"]) == [d2]


def test_phrase_owners_lists_every_owner(make_ability):
    a = make_ability(id="a", phrases=("x", "y"))
    b = make_ability(id="b", phrases=("y",))
    assert phrase_owners([a, b]) == {"x": [a], "y": [a, b]}


def test_ability_file_round_trip(make_ability):
    abilities = [make_ability(), make_ability(id="x", name="X", phrases=("x ray",))]
    assert parse_ability_file(ability_file(abilities, ["gone"])) == (abilities, ["gone"])


def test_parse_rejects_wrong_version():
    with pytest.raises(ValueError):
        parse_ability_file({"version": 99, "abilities": []})


def test_parse_rejects_malformed_entry():
    with pytest.raises((KeyError, TypeError, ValueError)):
        parse_ability_file({"version": 1, "abilities": [{"id": "x"}]})
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_jsonio.py tests/test_abilities.py -v`
Expected: FAIL. Collection errors `ModuleNotFoundError: No module named 'pvptimer.jsonio'` (and `pvptimer.abilities`, from conftest).

- [ ] **Step 4: Implement `src/pvptimer/jsonio.py`**

```python
"""Small JSON file helpers: crash-safe writes and quarantine of unreadable files."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_or_quarantine(path: Path, parse: Callable[[Any], T]) -> tuple[T | None, str | None]:
    """Parse a JSON file with parse().

    Returns (value, None) on success, (None, None) when the file does not exist, and
    (None, warning) after renaming an unreadable file to <name>.bad-<timestamp>.
    """
    if not path.exists():
        return None, None
    try:
        return parse(json.loads(path.read_text(encoding="utf-8"))), None
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bad = path.with_name(f"{path.name}.bad-{stamp}")
        os.replace(path, bad)
        return None, f"{path.name} could not be read ({exc}); moved it to {bad.name} and started fresh."
```

- [ ] **Step 5: Implement `src/pvptimer/abilities.py`**

```python
"""Ability data model and the pure rules around it (no Qt)."""
import re
from dataclasses import dataclass, replace
from typing import Any, Iterable

SLOTS = ("Q", "W", "E", "R", "D", "F", "Passive")
MAX_COOLDOWN_S = 600.0
RESERVED_WORD = "clear"
FORMAT_VERSION = 1


def normalize_phrase(text: str) -> str:
    """Lowercase, turn punctuation (except apostrophes) into spaces, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9'\s]", " ", text.lower())
    return " ".join(cleaned.split())


def make_id(name: str, existing: Iterable[str]) -> str:
    taken = set(existing)
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "ability"
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


@dataclass(frozen=True)
class Ability:
    id: str
    name: str
    slot: str
    cooldown_s: float
    phrases: tuple[str, ...]

    def normalized(self) -> "Ability":
        phrases = tuple(p for p in (normalize_phrase(x) for x in self.phrases) if p)
        return replace(self, name=self.name.strip(), phrases=phrases)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "slot": self.slot,
                "cooldown_s": self.cooldown_s, "phrases": list(self.phrases)}

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Ability":
        phrases = data["phrases"]
        if not isinstance(phrases, list):
            raise TypeError("phrases must be a list")
        return Ability(
            id=str(data["id"]),
            name=str(data["name"]),
            slot=str(data["slot"]),
            cooldown_s=float(data["cooldown_s"]),
            phrases=tuple(str(p) for p in phrases),
        ).normalized()


def validate(ability: Ability, others: Iterable[Ability]) -> list[str]:
    """Every problem with `ability`, given the current list (its own saved copy is ignored)."""
    a = ability.normalized()
    errors: list[str] = []
    if not a.name:
        errors.append("Name is required.")
    if a.slot not in SLOTS:
        errors.append(f"Slot must be one of: {', '.join(SLOTS)}.")
    if not (0 < a.cooldown_s <= MAX_COOLDOWN_S):
        errors.append(f"Cooldown must be greater than 0 and at most {MAX_COOLDOWN_S:g} seconds.")
    if not a.phrases:
        errors.append("At least one phrase is required.")
    owners = {p: o for o in others if o.id != a.id for p in o.normalized().phrases}
    seen: set[str] = set()
    for p in a.phrases:
        if p in seen:
            errors.append(f"Phrase '{p}' is listed twice.")
            continue
        seen.add(p)
        if p.split()[0] == RESERVED_WORD:
            errors.append(f"Phrase '{p}' starts with the reserved word '{RESERVED_WORD}'.")
        if p in owners:
            errors.append(f"Phrase '{p}' is already used by {owners[p].name}.")
    return errors


def merge(defaults: Iterable[Ability], user: Iterable[Ability], deleted_ids: Iterable[str]) -> list[Ability]:
    """Effective list: defaults (replaced by same-id user entries), then user-only entries,
    minus deleted ids."""
    user_by_id = {a.id: a for a in user}
    deleted = set(deleted_ids)
    result: list[Ability] = []
    default_ids: set[str] = set()
    for d in defaults:
        default_ids.add(d.id)
        if d.id not in deleted:
            result.append(user_by_id.get(d.id, d))
    result.extend(a for a in user_by_id.values() if a.id not in default_ids and a.id not in deleted)
    return result


def phrase_owners(abilities: Iterable[Ability]) -> dict[str, list[Ability]]:
    owners: dict[str, list[Ability]] = {}
    for a in abilities:
        for p in a.phrases:
            owners.setdefault(p, []).append(a)
    return owners


def parse_ability_file(data: Any) -> tuple[list[Ability], list[str]]:
    """Parse {"version", "abilities", optional "deleted_ids"}.
    Raises ValueError/TypeError/KeyError on a bad shape."""
    if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
        raise ValueError(f"not a PVPTimer ability file (expected version {FORMAT_VERSION})")
    abilities = [Ability.from_json(item) for item in data["abilities"]]
    deleted = [str(x) for x in data.get("deleted_ids", [])]
    return abilities, deleted


def ability_file(abilities: Iterable[Ability], deleted_ids: Iterable[str] = ()) -> dict[str, Any]:
    data: dict[str, Any] = {"version": FORMAT_VERSION, "abilities": [a.to_json() for a in abilities]}
    deleted = sorted(deleted_ids)
    if deleted:
        data["deleted_ids"] = deleted
    return data
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_jsonio.py tests/test_abilities.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add src/pvptimer/jsonio.py src/pvptimer/abilities.py tests
git commit -m "feat: ability model, validation, merge rules and JSON helpers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: AbilityStore

**Files:**
- Create: `src/pvptimer/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: everything in `abilities.py` and `jsonio.py` from Task 3.
- Produces: `AbilityStore(defaults_path: Path, user_path: Path)` (QObject) with signal `abilities_changed()`, attribute `warnings: list[str]`, and methods `load() -> None`, `abilities() -> list[Ability]` (sorted by name), `get(ability_id: str) -> Ability | None`, `match(text: str) -> Ability | None`, `phrases() -> list[str]`, `duplicate_phrases() -> set[str]`, `validate(ability) -> list[str]`, `upsert(ability) -> Ability` (raises `ValueError`; an empty `id` means a new ability), `delete(ability_id) -> None`, `export_file(path) -> None`, `import_file(path, replace_existing: Callable[[Ability, Ability], bool]) -> ImportResult`. Dataclass `ImportResult(added, replaced, kept, skipped: list[str])`.

- [ ] **Step 1: Write the failing test `tests/test_store.py`**

```python
import json

import pytest

from pvptimer.abilities import ability_file
from pvptimer.store import AbilityStore


@pytest.fixture
def files(tmp_path, make_ability):
    defaults = tmp_path / "defaults.json"
    user = tmp_path / "user" / "abilities.json"
    defaults.write_text(json.dumps(ability_file([
        make_ability(id="bloodletter_e", name="Bloodletter E", phrases=("blood letter e", "blood e")),
        make_ability(id="cleric_robe_r", name="Cleric Robe R", slot="R", cooldown_s=30.0,
                     phrases=("cleric robe r",)),
    ])), encoding="utf-8")
    return defaults, user


def new_store(files):
    store = AbilityStore(*files)
    store.load()
    return store


def test_load_defaults_without_user_file(files):
    store = new_store(files)
    assert [a.name for a in store.abilities()] == ["Bloodletter E", "Cleric Robe R"]
    assert store.warnings == []


def test_match_normalizes_text(files):
    store = new_store(files)
    assert store.match("Blood-Letter E!").id == "bloodletter_e"
    assert store.match("nothing") is None


def test_upsert_new_ability_assigns_id_persists_and_emits(files, make_ability):
    store = new_store(files)
    seen = []
    store.abilities_changed.connect(lambda: seen.append(True))
    stored = store.upsert(make_ability(id="", name="Hellion Hood D", slot="D", cooldown_s=25.0,
                                       phrases=("Hell Ion D",)))
    assert stored.id == "hellion_hood_d"
    assert stored.phrases == ("hell ion d",)
    assert seen == [True]
    assert new_store(files).match("hell ion d").id == "hellion_hood_d"


def test_upsert_invalid_raises_and_changes_nothing(files, make_ability):
    store = new_store(files)
    with pytest.raises(ValueError, match="already used by Bloodletter E"):
        store.upsert(make_ability(id="", name="Copy", phrases=("blood e",)))
    assert len(store.abilities()) == 2
    assert not files[1].exists()


def test_editing_a_default_writes_an_override_only(files, make_ability):
    defaults_before = files[0].read_text(encoding="utf-8")
    store = new_store(files)
    store.upsert(make_ability(id="cleric_robe_r", name="Cleric Robe R", slot="R", cooldown_s=25.0,
                              phrases=("robe r",)))
    assert files[0].read_text(encoding="utf-8") == defaults_before
    reloaded = new_store(files)
    assert reloaded.get("cleric_robe_r").cooldown_s == 25.0
    assert reloaded.match("cleric robe r") is None


def test_deleting_a_default_hides_it_after_reload(files):
    new_store(files).delete("cleric_robe_r")
    assert new_store(files).get("cleric_robe_r") is None


def test_deleting_a_user_ability_removes_it(files, make_ability):
    store = new_store(files)
    store.upsert(make_ability(id="", name="Mine", phrases=("mine",)))
    store.delete("mine")
    assert new_store(files).get("mine") is None


def test_new_ability_never_reuses_a_deleted_default_id(files, make_ability):
    store = new_store(files)
    store.delete("cleric_robe_r")
    stored = store.upsert(make_ability(id="", name="Cleric Robe R", slot="R", phrases=("robe r",)))
    assert stored.id == "cleric_robe_r_2"


def test_corrupt_user_file_is_quarantined_and_defaults_load(files):
    files[1].parent.mkdir(parents=True)
    files[1].write_text("{broken", encoding="utf-8")
    store = new_store(files)
    assert len(store.abilities()) == 2
    assert len(store.warnings) == 1
    assert list(files[1].parent.glob("abilities.json.bad-*"))


def test_duplicate_phrase_between_default_and_user_is_reported_and_first_owner_wins(files, make_ability):
    # A user phrase that a newer defaults file also uses.
    files[1].parent.mkdir(parents=True)
    files[1].write_text(json.dumps(ability_file([make_ability(id="mine", name="Mine", phrases=("blood e",))])),
                        encoding="utf-8")
    store = new_store(files)
    assert store.duplicate_phrases() == {"blood e"}
    assert store.match("blood e").id == "bloodletter_e"


def test_export_then_import_into_fresh_store(files, tmp_path, make_ability):
    store = new_store(files)
    store.upsert(make_ability(id="", name="Mine", phrases=("mine",)))
    export = tmp_path / "export.json"
    store.export_file(export)
    empty_defaults = tmp_path / "empty_defaults.json"
    empty_defaults.write_text(json.dumps(ability_file([])), encoding="utf-8")
    other = AbilityStore(empty_defaults, tmp_path / "other" / "abilities.json")
    other.load()
    result = other.import_file(export, replace_existing=lambda old, new: True)
    assert sorted(result.added) == ["Bloodletter E", "Cleric Robe R", "Mine"]
    assert other.match("mine").id == "mine"


def test_import_conflicts_ask_and_respect_answer(files, tmp_path, make_ability):
    incoming = tmp_path / "in.json"
    incoming.write_text(json.dumps(ability_file([
        make_ability(id="bloodletter_e", name="Bloodletter E", cooldown_s=99.0, phrases=("blood letter e",))
    ])), encoding="utf-8")
    store = new_store(files)
    kept = store.import_file(incoming, replace_existing=lambda old, new: False)
    assert kept.kept == ["Bloodletter E"]
    assert store.get("bloodletter_e").cooldown_s == 15.0
    replaced = store.import_file(incoming, replace_existing=lambda old, new: True)
    assert replaced.replaced == ["Bloodletter E"]
    assert store.get("bloodletter_e").cooldown_s == 99.0


def test_import_skips_invalid_entries(files, tmp_path, make_ability):
    incoming = tmp_path / "in.json"
    incoming.write_text(json.dumps(ability_file([make_ability(id="copy", name="Copy", phrases=("blood e",))])),
                        encoding="utf-8")
    store = new_store(files)
    result = store.import_file(incoming, replace_existing=lambda old, new: True)
    assert result.skipped == ["Copy: Phrase 'blood e' is already used by Bloodletter E."]
    assert store.get("copy") is None


def test_import_rejects_non_ability_file(files, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        new_store(files).import_file(bad, replace_existing=lambda old, new: True)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.store'`.

- [ ] **Step 3: Implement `src/pvptimer/store.py`**

```python
"""AbilityStore: the effective ability list, persisted as bundled defaults + per-user overrides."""
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from .abilities import (Ability, ability_file, make_id, merge, normalize_phrase,
                        parse_ability_file, phrase_owners, validate)
from .jsonio import atomic_write_json, load_or_quarantine


@dataclass
class ImportResult:
    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class AbilityStore(QObject):
    abilities_changed = Signal()

    def __init__(self, defaults_path: Path, user_path: Path) -> None:
        super().__init__()
        self._defaults_path = defaults_path
        self._user_path = user_path
        self._defaults: list[Ability] = []
        self._user: dict[str, Ability] = {}
        self._deleted: set[str] = set()
        self._effective: list[Ability] = []
        self._by_phrase: dict[str, Ability] = {}
        self.warnings: list[str] = []

    def load(self) -> None:
        self._defaults, _ = parse_ability_file(json.loads(self._defaults_path.read_text(encoding="utf-8")))
        parsed, warning = load_or_quarantine(self._user_path, parse_ability_file)
        if warning:
            self.warnings.append(warning)
        user, deleted = parsed if parsed else ([], [])
        self._user = {a.id: a for a in user}
        self._deleted = set(deleted)
        self._recompute()
        self.abilities_changed.emit()

    # queries ------------------------------------------------------------
    def abilities(self) -> list[Ability]:
        return sorted(self._effective, key=lambda a: a.name.casefold())

    def get(self, ability_id: str) -> Ability | None:
        return next((a for a in self._effective if a.id == ability_id), None)

    def match(self, text: str) -> Ability | None:
        return self._by_phrase.get(normalize_phrase(text))

    def phrases(self) -> list[str]:
        return list(self._by_phrase)

    def duplicate_phrases(self) -> set[str]:
        return {p for p, owners in phrase_owners(self._effective).items() if len(owners) > 1}

    def validate(self, ability: Ability) -> list[str]:
        return validate(ability, self._effective)

    # changes ------------------------------------------------------------
    def upsert(self, ability: Ability) -> Ability:
        """Validate and save. An empty id means a new ability; one is assigned.
        Raises ValueError listing every problem."""
        errors = self.validate(ability)
        if errors:
            raise ValueError("\n".join(errors))
        stored = ability.normalized()
        if not stored.id:
            stored = replace(stored, id=make_id(stored.name, self._all_ids()))
        self._user[stored.id] = stored
        self._deleted.discard(stored.id)
        self._commit()
        return stored

    def delete(self, ability_id: str) -> None:
        self._user.pop(ability_id, None)
        if any(d.id == ability_id for d in self._defaults):
            self._deleted.add(ability_id)
        self._commit()

    def export_file(self, path: Path) -> None:
        atomic_write_json(path, ability_file(self._effective))

    def import_file(self, path: Path, replace_existing: Callable[[Ability, Ability], bool]) -> ImportResult:
        """Add abilities from an exported file. replace_existing(existing, incoming) decides id clashes.
        Raises ValueError (or OSError) when the file is not a readable ability file."""
        incoming, _ = parse_ability_file(json.loads(path.read_text(encoding="utf-8")))
        result = ImportResult()
        for ability in incoming:
            if not ability.id:
                ability = replace(ability, id=make_id(ability.name, self._all_ids()))
            existing = self.get(ability.id)
            if existing is not None and not replace_existing(existing, ability):
                result.kept.append(ability.name)
                continue
            errors = validate(ability, self._effective)
            if errors:
                result.skipped.append(f"{ability.name}: {errors[0]}")
                continue
            self._user[ability.id] = ability
            self._deleted.discard(ability.id)
            self._recompute()
            (result.replaced if existing else result.added).append(ability.name)
        if result.added or result.replaced:
            self._commit()
        return result

    # internals ----------------------------------------------------------
    def _all_ids(self) -> set[str]:
        return {a.id for a in self._defaults} | set(self._user) | self._deleted

    def _recompute(self) -> None:
        self._effective = merge(self._defaults, self._user.values(), self._deleted)
        self._by_phrase = {}
        for a in self._effective:
            for p in a.phrases:
                self._by_phrase.setdefault(p, a)  # first owner wins if a phrase is duplicated

    def _commit(self) -> None:
        atomic_write_json(self._user_path, ability_file(self._user.values(), self._deleted))
        self._recompute()
        self.abilities_changed.emit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_store.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/store.py tests/test_store.py
git commit -m "feat: AbilityStore with defaults/user merge, import and export" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: TimerManager (pure)

**Files:**
- Create: `src/pvptimer/timers.py`
- Test: `tests/test_timers.py`

**Interfaces:**
- Produces: `TimerState` enum (`RUNNING`, `WARNING`, `READY`); frozen dataclass `TimerView(ability_id: str, name: str, remaining_s: float, fraction: float, state: TimerState)`; `TimerManager(clock=time.monotonic, speech_offset_s=0.7, warning_s=3.0, ready_display_s=3.0)`. Its three settings are public, writable attributes. Methods: `start(ability)` (anything with `.id`, `.name`, `.cooldown_s`), `clear(ability_id)`, `clear_all()`, `ready_events() -> list[str]`, `snapshot() -> list[TimerView]`. Call `ready_events()` before `snapshot()` on each tick.

- [ ] **Step 1: Write the failing test `tests/test_timers.py`**

```python
from types import SimpleNamespace

import pytest

from pvptimer.timers import TimerManager, TimerState


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def ability(id="bl", name="Bloodletter E", cooldown_s=15.0):
    return SimpleNamespace(id=id, name=name, cooldown_s=cooldown_s)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def timers(clock):
    return TimerManager(clock=clock, speech_offset_s=0.5, warning_s=3.0, ready_display_s=3.0)


def test_start_backdates_by_speech_offset(timers):
    timers.start(ability())
    [view] = timers.snapshot()
    assert view.remaining_s == pytest.approx(14.5)
    assert view.fraction == pytest.approx(14.5 / 15.0)
    assert view.state is TimerState.RUNNING
    assert view.name == "Bloodletter E"


@pytest.mark.parametrize("elapsed, state", [
    (11.49, TimerState.RUNNING),   # remaining 3.01
    (11.5, TimerState.WARNING),    # remaining exactly warning_s
    (14.4, TimerState.WARNING),
    (14.5, TimerState.READY),      # remaining exactly 0
    (17.49, TimerState.READY),
])
def test_state_boundaries(timers, clock, elapsed, state):
    timers.start(ability())
    clock.now += elapsed
    assert timers.snapshot()[0].state is state


def test_timer_removed_after_ready_display(timers, clock):
    timers.start(ability())
    clock.now += 14.5 + 3.0
    assert timers.snapshot() == []


def test_restart_replaces_existing_timer(timers, clock):
    timers.start(ability())
    clock.now += 10
    timers.start(ability())
    views = timers.snapshot()
    assert len(views) == 1
    assert views[0].remaining_s == pytest.approx(14.5)


def test_ready_event_fires_once_and_again_after_restart(timers, clock):
    timers.start(ability())
    clock.now += 14.0
    assert timers.ready_events() == []
    clock.now += 0.5
    assert timers.ready_events() == ["bl"]
    assert timers.ready_events() == []
    timers.start(ability())
    clock.now += 14.5
    assert timers.ready_events() == ["bl"]


def test_clear_and_clear_all(timers):
    timers.start(ability(id="a"))
    timers.start(ability(id="b"))
    timers.clear("a")
    assert [v.ability_id for v in timers.snapshot()] == ["b"]
    timers.clear("missing")
    timers.clear_all()
    assert timers.snapshot() == []


def test_snapshot_sorted_soonest_first(timers):
    timers.start(ability(id="long", cooldown_s=60))
    timers.start(ability(id="short", cooldown_s=10))
    assert [v.ability_id for v in timers.snapshot()] == ["short", "long"]


def test_offset_longer_than_cooldown_is_immediately_ready(timers):
    timers.start(ability(cooldown_s=0.3))
    [view] = timers.snapshot()
    assert view.state is TimerState.READY
    assert view.fraction == 0.0
    assert timers.ready_events() == ["bl"]
    assert timers.ready_events() == []


def test_setting_changes_apply_to_later_starts(timers):
    timers.speech_offset_s = 0.0
    timers.start(ability())
    assert timers.snapshot()[0].remaining_s == pytest.approx(15.0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_timers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.timers'`.

- [ ] **Step 3: Implement `src/pvptimer/timers.py`**

```python
"""Countdown state for enemy abilities. Pure logic: no Qt, clock injected for tests."""
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol


class TimerState(Enum):
    RUNNING = "running"
    WARNING = "warning"
    READY = "ready"


class Timed(Protocol):
    id: str
    name: str
    cooldown_s: float


@dataclass(frozen=True)
class TimerView:
    ability_id: str
    name: str
    remaining_s: float
    fraction: float  # remaining / cooldown, clamped to [0, 1]
    state: TimerState


@dataclass
class _Timer:
    ability_id: str
    name: str
    cooldown_s: float
    end: float
    ready_reported: bool = False


class TimerManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic, speech_offset_s: float = 0.7,
                 warning_s: float = 3.0, ready_display_s: float = 3.0) -> None:
        self._clock = clock
        self.speech_offset_s = speech_offset_s
        self.warning_s = warning_s
        self.ready_display_s = ready_display_s
        self._timers: dict[str, _Timer] = {}

    def start(self, ability: Timed) -> None:
        """Start, or restart, the timer for `ability`, backdated by the speech offset."""
        end = self._clock() - self.speech_offset_s + ability.cooldown_s
        self._timers[ability.id] = _Timer(ability.id, ability.name, ability.cooldown_s, end)

    def clear(self, ability_id: str) -> None:
        self._timers.pop(ability_id, None)

    def clear_all(self) -> None:
        self._timers.clear()

    def ready_events(self) -> list[str]:
        """Ids that reached zero since the last call. Call once per tick, before snapshot()."""
        now = self._clock()
        fired = []
        for t in self._timers.values():
            if not t.ready_reported and now >= t.end:
                t.ready_reported = True
                fired.append(t.ability_id)
        return fired

    def snapshot(self) -> list[TimerView]:
        """Current timers, soonest first. Drops timers whose READY display has ended."""
        now = self._clock()
        self._timers = {k: t for k, t in self._timers.items() if now < t.end + self.ready_display_s}
        return sorted((self._view(t, now) for t in self._timers.values()), key=lambda v: v.remaining_s)

    def _view(self, t: _Timer, now: float) -> TimerView:
        remaining = t.end - now
        if remaining <= 0:
            state = TimerState.READY
        elif remaining <= self.warning_s:
            state = TimerState.WARNING
        else:
            state = TimerState.RUNNING
        fraction = min(1.0, max(0.0, remaining / t.cooldown_s))
        return TimerView(t.ability_id, t.name, remaining, fraction, state)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_timers.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/timers.py tests/test_timers.py
git commit -m "feat: TimerManager with warning/ready states and injected clock" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Settings model (pure)

**Files:**
- Create: `src/pvptimer/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `jsonio.atomic_write_json`, `jsonio.load_or_quarantine`.
- Produces: `MOUSE_BUTTONS = ("x1", "x2", "middle")`; frozen `PttBinding(device: str, name: str)` with `.label()`, `.to_json()`, `PttBinding.from_json(data | None) -> PttBinding | None`; dataclass `OverlaySettings(screen=0, x=40, y=200, opacity=0.9)`; dataclass `Settings(ptt, mic_device, speech_offset_s, warning_s, ready_display_s, beep_enabled, beep_volume, overlay)` with `.to_json()` and `Settings.from_json(data)`; `load_settings(path) -> tuple[Settings, str | None]`; `save_settings(path, settings) -> None`.

- [ ] **Step 1: Write the failing test `tests/test_settings.py`**

```python
import json

from pvptimer.settings import OverlaySettings, PttBinding, Settings, load_settings, save_settings


def test_missing_file_gives_defaults(tmp_path):
    settings, warning = load_settings(tmp_path / "settings.json")
    assert warning is None
    assert settings == Settings()
    assert settings.ptt is None
    assert settings.speech_offset_s == 0.7
    assert settings.overlay == OverlaySettings(0, 40, 200, 0.9)


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(ptt=PttBinding("mouse", "x1"), mic_device="Headset Mic", speech_offset_s=1.0,
                 warning_s=5.0, ready_display_s=2.0, beep_enabled=False, beep_volume=0.3,
                 overlay=OverlaySettings(1, 10, 20, 0.5))
    save_settings(path, s)
    assert load_settings(path) == (s, None)


def test_file_shape_matches_spec(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(ptt=PttBinding("keyboard", "f8")))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["ptt"] == {"device": "keyboard", "key": "f8"}
    assert data["overlay"] == {"screen": 0, "x": 40, "y": 200, "opacity": 0.9}


def test_partial_file_fills_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"version": 1, "warning_s": 5}', encoding="utf-8")
    settings, warning = load_settings(path)
    assert warning is None
    assert settings.warning_s == 5.0
    assert settings.beep_volume == 0.6


def test_invalid_file_is_quarantined(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"version": 1, "ptt": {"device": "mouse", "button": "left"}}', encoding="utf-8")
    settings, warning = load_settings(path)
    assert settings == Settings()
    assert warning
    assert not path.exists()


def test_binding_labels():
    assert PttBinding("mouse", "x1").label() == "Mouse X1"
    assert PttBinding("keyboard", "f8").label() == "Key F8"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.settings'`.

- [ ] **Step 3: Implement `src/pvptimer/settings.py`**

```python
"""User settings stored in settings.json (pure data; the dialog lives in settings_dialog.py)."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .jsonio import atomic_write_json, load_or_quarantine

SETTINGS_VERSION = 1
MOUSE_BUTTONS = ("x1", "x2", "middle")


@dataclass(frozen=True)
class PttBinding:
    device: str  # "keyboard" or "mouse"
    name: str    # pynput key name ("f8", "v", "vk:123") or a mouse button from MOUSE_BUTTONS

    def label(self) -> str:
        prefix = "Mouse" if self.device == "mouse" else "Key"
        return f"{prefix} {self.name.upper()}"

    def to_json(self) -> dict[str, str]:
        if self.device == "mouse":
            return {"device": "mouse", "button": self.name}
        return {"device": "keyboard", "key": self.name}

    @staticmethod
    def from_json(data: Any) -> "PttBinding | None":
        if data is None:
            return None
        device = data["device"]
        if device == "mouse":
            button = str(data["button"])
            if button not in MOUSE_BUTTONS:
                raise ValueError(f"unknown mouse button {button!r}")
            return PttBinding("mouse", button)
        if device == "keyboard":
            return PttBinding("keyboard", str(data["key"]))
        raise ValueError(f"unknown push-to-talk device {device!r}")


@dataclass
class OverlaySettings:
    screen: int = 0
    x: int = 40
    y: int = 200
    opacity: float = 0.9


@dataclass
class Settings:
    ptt: PttBinding | None = None
    mic_device: str | None = None
    speech_offset_s: float = 0.7
    warning_s: float = 3.0
    ready_display_s: float = 3.0
    beep_enabled: bool = True
    beep_volume: float = 0.6
    overlay: OverlaySettings = field(default_factory=OverlaySettings)

    def to_json(self) -> dict[str, Any]:
        return {
            "version": SETTINGS_VERSION,
            "ptt": self.ptt.to_json() if self.ptt else None,
            "mic_device": self.mic_device,
            "speech_offset_s": self.speech_offset_s,
            "warning_s": self.warning_s,
            "ready_display_s": self.ready_display_s,
            "beep_enabled": self.beep_enabled,
            "beep_volume": self.beep_volume,
            "overlay": asdict(self.overlay),
        }

    @staticmethod
    def from_json(data: Any) -> "Settings":
        if not isinstance(data, dict):
            raise TypeError("settings must be a JSON object")
        d, od = Settings(), OverlaySettings()
        mic = data.get("mic_device")
        if mic is not None and not isinstance(mic, str):
            raise TypeError("mic_device must be a string or null")
        ov = data.get("overlay", {})
        return Settings(
            ptt=PttBinding.from_json(data.get("ptt")),
            mic_device=mic,
            speech_offset_s=float(data.get("speech_offset_s", d.speech_offset_s)),
            warning_s=float(data.get("warning_s", d.warning_s)),
            ready_display_s=float(data.get("ready_display_s", d.ready_display_s)),
            beep_enabled=bool(data.get("beep_enabled", d.beep_enabled)),
            beep_volume=float(data.get("beep_volume", d.beep_volume)),
            overlay=OverlaySettings(
                screen=int(ov.get("screen", od.screen)),
                x=int(ov.get("x", od.x)),
                y=int(ov.get("y", od.y)),
                opacity=float(ov.get("opacity", od.opacity)),
            ),
        )


def load_settings(path: Path) -> tuple[Settings, str | None]:
    settings, warning = load_or_quarantine(path, Settings.from_json)
    return settings or Settings(), warning


def save_settings(path: Path, settings: Settings) -> None:
    atomic_write_json(path, settings.to_json())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_settings.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/settings.py tests/test_settings.py
git commit -m "feat: settings model with defaults, validation and persistence" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Phrase router (pure)

**Files:**
- Create: `src/pvptimer/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `abilities.Ability`, `abilities.RESERVED_WORD`, `abilities.normalize_phrase`.
- Produces: `Action` enum (`TEST_RESULT`, `CLEAR_ALL`, `CLEAR`, `START`, `NO_MATCH`); frozen `Decision(action: Action, text: str, ability: Ability | None = None)`; `decide(text: str, match: Callable[[str], Ability | None], test_mode: bool) -> Decision`. `Decision.text` is always normalized.

- [ ] **Step 1: Write the failing test `tests/test_router.py`**

```python
import pytest

from pvptimer.router import Action, decide


@pytest.fixture
def match(make_ability):
    table = {
        "blood letter e": make_ability(),
        "cleric robe r": make_ability(id="robe", name="Cleric Robe R", slot="R", phrases=("cleric robe r",)),
    }
    return table.get


def test_known_phrase_starts_timer(match):
    d = decide("Blood Letter E", match, test_mode=False)
    assert d.action is Action.START and d.ability.id == "bloodletter_e" and d.text == "blood letter e"


def test_unknown_phrase_is_no_match(match):
    d = decide("hello", match, False)
    assert d.action is Action.NO_MATCH and d.text == "hello" and d.ability is None


def test_empty_text_is_no_match(match):
    d = decide("", match, False)
    assert d.action is Action.NO_MATCH and d.text == ""


def test_clear_all(match):
    assert decide("clear all", match, False).action is Action.CLEAR_ALL


def test_clear_phrase(match):
    d = decide("clear cleric robe r", match, False)
    assert d.action is Action.CLEAR and d.ability.id == "robe"


@pytest.mark.parametrize("text", ["clear nothing", "clear"])
def test_clear_unknown_is_no_match(match, text):
    assert decide(text, match, False).action is Action.NO_MATCH


@pytest.mark.parametrize("text, ability_id", [
    ("blood letter e", "bloodletter_e"),
    ("clear all", None),
    ("", None),
])
def test_test_mode_reports_match_without_acting(match, text, ability_id):
    d = decide(text, match, test_mode=True)
    assert d.action is Action.TEST_RESULT
    assert (d.ability.id if d.ability else None) == ability_id
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.router'`.

- [ ] **Step 3: Implement `src/pvptimer/router.py`**

```python
"""Decides what a recognized phrase means. A pure function so it is unit-testable."""
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .abilities import RESERVED_WORD, Ability, normalize_phrase


class Action(Enum):
    TEST_RESULT = "test_result"
    CLEAR_ALL = "clear_all"
    CLEAR = "clear"
    START = "start"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class Decision:
    action: Action
    text: str
    ability: Ability | None = None


def decide(text: str, match: Callable[[str], Ability | None], test_mode: bool) -> Decision:
    text = normalize_phrase(text)
    if test_mode:
        return Decision(Action.TEST_RESULT, text, match(text) if text else None)
    if not text:
        return Decision(Action.NO_MATCH, text)
    if text == f"{RESERVED_WORD} all":
        return Decision(Action.CLEAR_ALL, text)
    head, _, rest = text.partition(" ")
    if head == RESERVED_WORD and rest:
        target = match(rest)
        return Decision(Action.CLEAR, text, target) if target else Decision(Action.NO_MATCH, text)
    ability = match(text)
    return Decision(Action.START, text, ability) if ability else Decision(Action.NO_MATCH, text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_router.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/router.py tests/test_router.py
git commit -m "feat: phrase router for start/clear/test decisions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Overlay, beep, and tray app skeleton (in-game visual check)

**Files:**
- Create: `src/pvptimer/overlay.py`, `src/pvptimer/beep.py`, `src/pvptimer/app.py` (skeleton, replaced in Task 13), `src/pvptimer/__main__.py`
- Test: `tests/test_overlay.py`

**Interfaces:**
- Consumes: `TimerManager`, `TimerState`, `TimerView` (Task 5); `OverlaySettings`, `load_settings`, `save_settings` (Task 6); `paths` (Task 1).
- Produces: `format_remaining(remaining_s: float) -> str`; `resolve_position(screens: list[QRect], screen: int, x: int, y: int) -> QPoint`; `relative_position(screens: list[QRect], point: QPoint) -> tuple[int, int, int]`; `OverlayWindow(timers: TimerManager, settings: OverlaySettings)` (QWidget) with signal `position_changed(int, int, int)` and methods `apply_settings(OverlaySettings)`, `set_move_mode(bool)`, `show_heard(str)`; `ReadyBeep(wav: Path, volume: float, enabled: bool)` with `configure(volume, enabled)` and `play()`; `app.main() -> int`; `app.make_icon() -> QIcon`.

- [ ] **Step 1: Write the failing test `tests/test_overlay.py`**

```python
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect

from pvptimer.overlay import OverlayWindow, format_remaining, relative_position, resolve_position
from pvptimer.settings import OverlaySettings
from pvptimer.timers import TimerManager

SCREENS = [QRect(0, 0, 1920, 1080), QRect(1920, 0, 2560, 1440)]


@pytest.mark.parametrize("remaining, text", [
    (0, "READY"), (-1.2, "READY"), (4.31, "4.3"), (9.94, "9.9"), (10.0, "10"), (14.2, "15"),
])
def test_format_remaining(remaining, text):
    assert format_remaining(remaining) == text


def test_resolve_position_on_saved_screen():
    assert resolve_position(SCREENS, 1, 100, 50) == QPoint(2020, 50)


def test_resolve_position_falls_back_when_screen_missing():
    assert resolve_position(SCREENS, 5, 100, 50) == QPoint(40, 200)


def test_resolve_position_falls_back_when_offscreen():
    assert resolve_position(SCREENS, 0, 5000, 50) == QPoint(40, 200)


def test_relative_position_finds_screen():
    assert relative_position(SCREENS, QPoint(2020, 50)) == (1, 100, 50)
    assert relative_position(SCREENS, QPoint(-500, -500)) == (0, -500, -500)


def test_overlay_paints_every_state_without_errors(qtbot):
    clock = SimpleNamespace(now=0.0)
    timers = TimerManager(clock=lambda: clock.now, speech_offset_s=0.0)
    for ability_id, cooldown in [("run", 30), ("warn", 2), ("ready", 0.001)]:
        timers.start(SimpleNamespace(id=ability_id, name=ability_id.title(), cooldown_s=cooldown))
    clock.now = 0.01
    window = OverlayWindow(timers, OverlaySettings())
    qtbot.addWidget(window)
    window.show_heard("")
    assert not window.grab().isNull()
    window.show_heard("hello there")
    window.set_move_mode(True)
    assert not window.grab().isNull()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_overlay.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.overlay'`.

- [ ] **Step 3: Implement `src/pvptimer/overlay.py`**

```python
"""Transparent, always-on-top, click-through window that draws the active timers."""
import math
import time

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .settings import OverlaySettings
from .timers import TimerManager, TimerState, TimerView

ROW_W, ROW_H, ROW_GAP = 260, 26, 4
MAX_ROWS = 12
HEARD_S = 1.5
FADE_S = 1.0
RADIUS = 5.0
BACKGROUND = QColor(15, 23, 42, 190)
TEXT = QColor(241, 245, 249)
MUTED = QColor(203, 213, 225)
STATE_COLORS = {
    TimerState.RUNNING: QColor(100, 116, 139),
    TimerState.WARNING: QColor(245, 158, 11),
    TimerState.READY: QColor(34, 197, 94),
}
MOVE_SAMPLE = TimerView("sample", "Drag me", 12.0, 0.6, TimerState.RUNNING)
LEFT = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
RIGHT = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight


def format_remaining(remaining_s: float) -> str:
    if remaining_s <= 0:
        return "READY"
    if remaining_s < 10:
        return f"{remaining_s:.1f}"
    return str(math.ceil(remaining_s))


def resolve_position(screens: list[QRect], screen: int, x: int, y: int) -> QPoint:
    """Global top-left for a saved (screen, x, y). Falls back to the first screen at the
    default offset when the saved screen is gone or the point is off that screen."""
    if 0 <= screen < len(screens):
        geometry = screens[screen]
        point = geometry.topLeft() + QPoint(x, y)
        if geometry.contains(point):
            return point
    default = OverlaySettings()
    origin = screens[0].topLeft() if screens else QPoint(0, 0)
    return origin + QPoint(default.x, default.y)


def relative_position(screens: list[QRect], point: QPoint) -> tuple[int, int, int]:
    """(screen index, x, y relative to that screen) for a global point."""
    for index, geometry in enumerate(screens):
        if geometry.contains(point):
            return index, point.x() - geometry.x(), point.y() - geometry.y()
    origin = screens[0].topLeft() if screens else QPoint(0, 0)
    return 0, point.x() - origin.x(), point.y() - origin.y()


class OverlayWindow(QWidget):
    position_changed = Signal(int, int, int)  # screen index, x, y relative to that screen

    def __init__(self, timers: TimerManager, settings: OverlaySettings) -> None:
        super().__init__(None)
        self._timers = timers
        self._move_mode = False
        self._drag_offset: QPoint | None = None
        self._heard_text = ""
        self._heard_until = 0.0
        self.setWindowTitle("PVPTimer overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(ROW_W, (ROW_H + ROW_GAP) * (MAX_ROWS + 1))
        self._apply_flags()
        self.apply_settings(settings)

    def apply_settings(self, settings: OverlaySettings) -> None:
        self.setWindowOpacity(settings.opacity)
        self.move(resolve_position(self._screens(), settings.screen, settings.x, settings.y))

    def set_move_mode(self, on: bool) -> None:
        if on == self._move_mode:
            return
        was_visible = self.isVisible()
        self._move_mode = on
        self._apply_flags()
        if was_visible:
            self.show()  # changing window flags hides the window
        if not on:
            self.position_changed.emit(*relative_position(self._screens(), self.pos()))
        self.update()

    def show_heard(self, text: str) -> None:
        self._heard_text = text
        self._heard_until = time.monotonic() + HEARD_S
        self.update()

    # window setup -------------------------------------------------------
    def _apply_flags(self) -> None:
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        if not self._move_mode:
            flags |= Qt.WindowType.WindowTransparentForInput  # clicks go through to the game
        self.setWindowFlags(flags)

    @staticmethod
    def _screens() -> list[QRect]:
        return [s.geometry() for s in QGuiApplication.screens()]

    # dragging (only possible in move mode, when the window accepts input) ---
    def mousePressEvent(self, event) -> None:
        if self._move_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self.position_changed.emit(*relative_position(self._screens(), self.pos()))

    # painting -----------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        views = self._timers.snapshot()[:MAX_ROWS]
        if self._move_mode:
            painter.setPen(QPen(TEXT, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            views = views or [MOVE_SAMPLE]

        y = 0.0
        for view in views:
            self._draw_row(painter, QRectF(0, y, ROW_W, ROW_H), view)
            y += ROW_H + ROW_GAP
        if time.monotonic() < self._heard_until:
            self._draw_heard(painter, QRectF(0, y, ROW_W, ROW_H))
        painter.end()

    def _draw_row(self, painter: QPainter, rect: QRectF, view: TimerView) -> None:
        color = QColor(STATE_COLORS[view.state])
        fill_width = rect.width() * view.fraction
        opacity = 1.0
        if view.state is TimerState.READY:
            since_ready = -view.remaining_s
            opacity = max(0.0, min(1.0, (self._timers.ready_display_s - since_ready) / FADE_S))
            color.setAlphaF(0.55 + 0.45 * abs(math.cos(since_ready * math.pi * 2)))  # pulse
            fill_width = rect.width()
        painter.setOpacity(opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(rect.x(), rect.y(), fill_width, rect.height()), RADIUS, RADIUS)
        text_rect = rect.adjusted(8, 0, -8, 0)
        name = painter.fontMetrics().elidedText(view.name, Qt.TextElideMode.ElideRight,
                                                int(text_rect.width()) - 56)
        painter.setPen(TEXT)
        painter.drawText(text_rect, LEFT, name)
        painter.drawText(text_rect, RIGHT, format_remaining(view.remaining_s))
        painter.setOpacity(1.0)

    def _draw_heard(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        text = f'? heard: "{self._heard_text}"' if self._heard_text else "? heard nothing"
        text_rect = rect.adjusted(8, 0, -8, 0)
        painter.setPen(MUTED)
        painter.drawText(text_rect, LEFT, painter.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, int(text_rect.width())))
```

- [ ] **Step 4: Implement `src/pvptimer/beep.py`**

```python
"""Ready sound played through Qt Multimedia."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect


class ReadyBeep:
    def __init__(self, wav: Path, volume: float, enabled: bool) -> None:
        self._effect = QSoundEffect()
        self._effect.setSource(QUrl.fromLocalFile(str(wav)))
        self._enabled = enabled
        self.configure(volume, enabled)

    def configure(self, volume: float, enabled: bool) -> None:
        self._effect.setVolume(volume)
        self._enabled = enabled

    def play(self) -> None:
        if self._enabled:
            self._effect.play()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_overlay.py -v`
Expected: all passed.

- [ ] **Step 6: Implement the skeleton `src/pvptimer/app.py` and `src/pvptimer/__main__.py`**

`src/pvptimer/app.py` (Task 13 replaces this whole file):
```python
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
```

`src/pvptimer/__main__.py`:
```python
from pvptimer.app import main

raise SystemExit(main())
```

- [ ] **Step 7: Manual check: launch and use the debug timer**

Run: `.venv/Scripts/python -m pvptimer`
Expected: an amber clock icon appears in the system tray (it may be in the ^ overflow).
- Right-click the tray icon → **Debug: fire test timer**. A "Test timer" bar appears at about (40, 200) on the primary screen and counts down from about 7.3. It turns amber at 3.0, then pulses green with READY and a two-tone beep, then fades and disappears about 3 s later.
- Clicking on the bar clicks through to whatever is behind it, and the overlay never takes keyboard focus.
- Tray → **Move overlay** (checked): a dashed border and a "Drag me" row appear. Drag it somewhere, then uncheck **Move overlay**. Quit, relaunch, and confirm the overlay reopens at the new spot.

- [ ] **Step 8: HUMAN STEP: in-game check**

Ask the user to launch Albion in **borderless fullscreen**, start `.venv/Scripts/python -m pvptimer`, fire the debug timer, and confirm: the overlay is visible above the game, clicks pass through, the game keeps focus, and the beep is audible. Record any problem before continuing.

- [ ] **Step 9: Run the full suite, then commit**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all passed.

```bash
git add src/pvptimer tests/test_overlay.py
git commit -m "feat: click-through overlay, ready beep and tray skeleton with debug timer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Push-to-talk listener

**Files:**
- Create: `src/pvptimer/hotkey.py`
- Test: `tests/test_hotkey.py`

**Interfaces:**
- Consumes: `settings.PttBinding`, `settings.MOUSE_BUTTONS`.
- Produces: `key_to_name(key) -> str | None`; `button_to_name(button) -> str | None`; `PttState(binding)` with `.press(device, name) -> bool`, `.release(device, name) -> bool`, `.is_down`; `PttListener()` (QObject) with signals `ptt_down()`, `ptt_up()`, `captured(object)` (a `PttBinding`), `capture_cancelled()`, `failed(str)` and methods `start(binding | None)`, `stop()`, `capture_next()`, `cancel_capture()`.

- [ ] **Step 1: Write the failing test `tests/test_hotkey.py`**

```python
from pynput import keyboard, mouse

from pvptimer.hotkey import PttState, button_to_name, key_to_name
from pvptimer.settings import PttBinding


def test_key_to_name():
    assert key_to_name(keyboard.Key.f8) == "f8"
    assert key_to_name(keyboard.KeyCode.from_char("V")) == "v"
    assert key_to_name(keyboard.KeyCode.from_vk(200)) == "vk:200"


def test_button_to_name_only_accepts_bindable_buttons():
    assert button_to_name(mouse.Button.x1) == "x1"
    assert button_to_name(mouse.Button.middle) == "middle"
    assert button_to_name(mouse.Button.left) is None


def test_press_and_release_fire_once_and_ignore_auto_repeat():
    state = PttState(PttBinding("keyboard", "f8"))
    assert state.press("keyboard", "f8") is True
    assert state.press("keyboard", "f8") is False  # auto-repeat
    assert state.release("keyboard", "f8") is True
    assert state.release("keyboard", "f8") is False


def test_other_keys_and_devices_are_ignored():
    state = PttState(PttBinding("mouse", "x1"))
    assert state.press("keyboard", "x1") is False
    assert state.press("mouse", "x2") is False
    assert state.press("mouse", None) is False
    assert state.release("mouse", "x1") is False  # release without press


def test_no_binding_never_fires():
    state = PttState(None)
    assert state.press("keyboard", "f8") is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_hotkey.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.hotkey'`.

- [ ] **Step 3: Implement `src/pvptimer/hotkey.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_hotkey.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/hotkey.py tests/test_hotkey.py
git commit -m "feat: global push-to-talk listener with key capture" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Speech worker

**Files:**
- Create: `src/pvptimer/speech.py`
- Test: `tests/test_speech.py`

**Interfaces:**
- Consumes: `abilities.RESERVED_WORD`, `abilities.normalize_phrase`; `paths.model_dir` (tests only); Vosk's `Model.vosk_model_find_word` (confirmed in Task 2).
- Produces: `build_grammar(phrases: Iterable[str], is_known: Callable[[str], bool]) -> list[str]`; `extract_text(result_json: str) -> str`; `resolve_input_device(name: str | None, devices: list[dict]) -> int | None`; `input_device_names(devices: list[dict]) -> list[str]`; `SpeechWorker(model_path: Path, mic_device: str | None)` (QObject meant for a QThread) with signals `recognized(str)`, `model_ready()`, `error(str)`; slots `start()`, `set_phrases(list)`, `set_mic_device(object)`, `on_ptt_down()`, `on_ptt_up()`; plain methods `is_known(word) -> bool`, `unknown_words(phrases) -> set[str]`, `stop()`.

- [ ] **Step 1: Write the failing test `tests/test_speech.py`**

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_speech.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.speech'`.

- [ ] **Step 3: Implement `src/pvptimer/speech.py`**

```python
"""Offline speech recognition with Vosk, gated by push-to-talk.

SpeechWorker lives on its own QThread. The sounddevice callback (PortAudio's thread) only
queues audio while push-to-talk is held. The worker feeds that audio to Vosk every 50 ms
and emits the final text shortly after the key is released.
"""
import json
import logging
import queue
import threading
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .abilities import RESERVED_WORD, normalize_phrase

SAMPLE_RATE = 16000
BLOCK_SIZE = 800          # 50 ms of audio per callback
FEED_INTERVAL_MS = 50
PTT_TAIL_MS = 150         # keep recording briefly after release so the last syllable isn't cut off
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
    return normalize_phrase(" ".join(w for w in text.split() if w != "[unk]"))


def resolve_input_device(name: str | None, devices: list[dict]) -> int | None:
    """Index of the first input device with exactly this name, else None (system default).
    Windows lists one microphone once per audio API, so names repeat; the first wins."""
    if name is None:
        return None
    for index, device in enumerate(devices):
        if device["name"] == name and device["max_input_channels"] > 0:
            return index
    return None


def input_device_names(devices: list[dict]) -> list[str]:
    names: list[str] = []
    for device in devices:
        if device["max_input_channels"] > 0 and device["name"] not in names:
            names.append(device["name"])
    return names


class SpeechWorker(QObject):
    recognized = Signal(str)
    model_ready = Signal()
    error = Signal(str)

    def __init__(self, model_path: Path, mic_device: str | None) -> None:
        super().__init__()
        self._model_path = model_path
        self._mic_device = mic_device
        self._model = None
        self._recognizer = None
        self._phrases: list[str] = []
        self._parts: list[str] = []
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
        self._feed_timer = QTimer(self)
        self._feed_timer.setInterval(FEED_INTERVAL_MS)
        self._feed_timer.timeout.connect(self._feed)
        self._finalize_timer = QTimer(self)
        self._finalize_timer.setSingleShot(True)
        self._finalize_timer.setInterval(PTT_TAIL_MS)
        self._finalize_timer.timeout.connect(self._finalize)

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
        self.model_ready.emit()

    def stop(self) -> None:
        """Call from the main thread after the worker thread has finished."""
        self._listening.clear()
        self._close_stream()

    @Slot(list)
    def set_phrases(self, phrases: list) -> None:
        self._phrases = [str(p) for p in phrases]
        self._rebuild_recognizer()

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
        index = resolve_input_device(self._mic_device, list(sd.query_devices()))
        if self._mic_device is not None and index is None:
            self.error.emit(f"Microphone '{self._mic_device}' not found; using the system default.")
        for device in ([index, None] if index is not None else [None]):
            try:
                self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                                                 dtype="int16", channels=1, device=device,
                                                 callback=self._on_audio)
                self._stream.start()
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
        if self._recognizer is None:
            return
        if self._finalize_timer.isActive():  # pressed again during the tail: finish the last one
            self._finalize_timer.stop()
            self._finalize()
        self._drain(feed=False)
        self._recognizer.Reset()
        self._parts = []
        self._listening.set()
        self._feed_timer.start()

    @Slot()
    def on_ptt_up(self) -> None:
        if self._recognizer is None or not self._listening.is_set():
            return
        self._finalize_timer.start()

    def _feed(self) -> None:
        self._drain(feed=True)

    def _drain(self, feed: bool) -> None:
        while True:
            try:
                chunk = self._audio.get_nowait()
            except queue.Empty:
                return
            if feed and self._recognizer.AcceptWaveform(chunk):
                # Vosk found a pause mid-phrase; keep that part and continue.
                part = extract_text(self._recognizer.Result())
                if part:
                    self._parts.append(part)

    def _finalize(self) -> None:
        self._listening.clear()
        self._feed_timer.stop()
        self._drain(feed=True)
        text = normalize_phrase(" ".join([*self._parts, extract_text(self._recognizer.FinalResult())]))
        self._recognizer.Reset()
        self._parts = []
        self.recognized.emit(text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_speech.py -v`
Expected: all passed. `test_real_model_vocabulary_lookup` runs (not skipped) because Task 1 downloaded the model.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/speech.py tests/test_speech.py
git commit -m "feat: push-to-talk gated Vosk speech worker with grammar and mic selection" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Settings dialog

**Files:**
- Create: `src/pvptimer/settings_dialog.py`
- Test: `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: `Settings`, `PttBinding`, `OverlaySettings` (Task 6); `PttListener` (Task 9: `capture_next()`, `cancel_capture()`, signals `captured`, `capture_cancelled`).
- Produces: `SettingsDialog(settings: Settings, input_devices: list[str], ptt: PttListener | None, parent=None)` (QDialog) with public widgets `ptt_button`, `mic_combo`, `offset_spin`, `warning_spin`, `ready_spin`, `beep_check`, `volume_slider`, `opacity_slider`, `ok_button`, and the method `result_settings() -> Settings`.

- [ ] **Step 1: Write the failing test `tests/test_settings_dialog.py`**

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_settings_dialog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.settings_dialog'`.

- [ ] **Step 3: Implement `src/pvptimer/settings_dialog.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_settings_dialog.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/settings_dialog.py tests/test_settings_dialog.py
git commit -m "feat: settings dialog with push-to-talk capture and mic selection" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Ability editor

**Files:**
- Create: `src/pvptimer/editor.py`
- Test: `tests/test_editor.py`

**Interfaces:**
- Consumes: `AbilityStore` (Task 4: `abilities()`, `get()`, `validate()`, `upsert()`, `delete()`, `duplicate_phrases()`, `import_file()`, `export_file()`, signal `abilities_changed`); `Ability`, `SLOTS`, `MAX_COOLDOWN_S` (Task 3). Its `unknown_words` callable comes from `SpeechWorker.unknown_words` (Task 10).
- Produces: `ability_status(ability, unknown_words, duplicates) -> tuple[str, str]`; `describe_test_result(text: str, matched: Ability | None, editing_id: str, dirty: bool) -> str`; `EditorWindow(store, unknown_words)` (QWidget) with signal `test_requested()`, methods `refresh()`, `show_test_result(text: str, matched: Ability | None)`, `form_ability() -> Ability`, `is_dirty() -> bool`, and public widgets `table`, `add_button`, `delete_button`, `import_button`, `export_button`, `search_edit`, `name_edit`, `slot_combo`, `cooldown_spin`, `phrases_edit`, `errors_label`, `save_button`, `revert_button`, `test_button`, `test_label`.

UI note: the spec's mock-up shows one input row per phrase. This plan uses a single multi-line box with one phrase per line. It does the same job with far less widget code.

- [ ] **Step 1: Write the failing test `tests/test_editor.py`**

```python
import json

import pytest
from PySide6.QtWidgets import QMessageBox

from pvptimer.abilities import ability_file
from pvptimer.editor import EditorWindow, ability_status, describe_test_result
from pvptimer.store import AbilityStore


def fake_unknown(phrases):
    return {w for p in phrases for w in p.split() if w == "hellion"}


@pytest.fixture
def store(tmp_path, make_ability):
    defaults = tmp_path / "defaults.json"
    defaults.write_text(json.dumps(ability_file([
        make_ability(phrases=("blood letter e", "blood e")),
        make_ability(id="hellion_hood_d", name="Hellion Hood D", slot="D", cooldown_s=25.0,
                     phrases=("hellion d",)),
    ])), encoding="utf-8")
    s = AbilityStore(defaults, tmp_path / "user.json")
    s.load()
    return s


@pytest.fixture
def editor(qtbot, store):
    window = EditorWindow(store, fake_unknown)
    qtbot.addWidget(window)
    return window


def column(editor, index):
    return [editor.table.item(r, index).text() for r in range(editor.table.rowCount())]


def test_ability_status(make_ability):
    assert ability_status(make_ability(phrases=("blood e", "hellion e")), fake_unknown, set())[0] == "⚠ word"
    b = make_ability(phrases=("blood e",))
    assert ability_status(b, fake_unknown, {"blood e"}) == ("⚠ dup", "Also used by another ability: blood e")
    assert ability_status(b, fake_unknown, set()) == ("✓", "")


def test_describe_test_result(make_ability):
    bl = make_ability()
    assert describe_test_result("", None, "bloodletter_e", False) == "Heard nothing — try again."
    assert describe_test_result("hello", None, "x", False) == 'Heard: "hello" → ✗ no match'
    assert describe_test_result("blood e", bl, "bloodletter_e", False) == 'Heard: "blood e" → ✓ matches Bloodletter E'
    assert describe_test_result("blood e", bl, "other", False) == \
        'Heard: "blood e" → matches a different ability: Bloodletter E'
    assert describe_test_result("blood e", bl, "bloodletter_e", True).endswith(
        "(unsaved changes can't be heard until you Save)")


def test_table_lists_abilities_with_status(editor):
    assert column(editor, 0) == ["Bloodletter E", "Hellion Hood D"]
    assert column(editor, 3) == ["blood letter e, blood e", "hellion d"]
    assert column(editor, 4) == ["✓", "⚠ word"]
    assert "hellion" in editor.table.item(1, 4).toolTip()


def test_new_ability_form_validates_then_saves(editor, store):
    editor.add_button.click()
    assert not editor.save_button.isEnabled()
    editor.name_edit.setText("Cleric Robe R")
    editor.slot_combo.setCurrentText("R")
    editor.cooldown_spin.setValue(30.0)
    editor.phrases_edit.setPlainText("blood e")
    assert "already used by Bloodletter E" in editor.errors_label.text()
    assert not editor.save_button.isEnabled()
    editor.phrases_edit.setPlainText("cleric robe r\nrobe r")
    assert editor.errors_label.text() == ""
    assert editor.save_button.isEnabled()
    editor.save_button.click()
    saved = store.get("cleric_robe_r")
    assert saved.phrases == ("cleric robe r", "robe r") and saved.cooldown_s == 30.0
    assert "Cleric Robe R" in column(editor, 0)
    assert not editor.save_button.isEnabled()  # saved form is no longer dirty


def test_selecting_a_row_loads_it_and_revert_discards_edits(editor):
    editor.table.selectRow(0)
    assert editor.name_edit.text() == "Bloodletter E"
    assert not editor.save_button.isEnabled()
    editor.cooldown_spin.setValue(20.0)
    assert editor.save_button.isEnabled()
    editor.revert_button.click()
    assert editor.cooldown_spin.value() == 15.0


def test_search_hides_non_matching_rows(editor):
    editor.search_edit.setText("hell")
    assert [editor.table.isRowHidden(r) for r in range(2)] == [True, False]
    editor.search_edit.setText("blood e")  # phrases are searched too
    assert [editor.table.isRowHidden(r) for r in range(2)] == [False, True]


def test_delete_asks_then_removes(editor, store, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    editor.table.selectRow(1)
    editor.delete_button.click()
    assert store.get("hellion_hood_d") is None
    assert column(editor, 0) == ["Bloodletter E"]


def test_test_result_is_shown_only_while_waiting(qtbot, editor, store):
    editor.table.selectRow(0)
    editor.show_test_result("blood e", store.get("bloodletter_e"))
    assert editor.test_label.text() == ""  # not waiting: ignored
    with qtbot.waitSignal(editor.test_requested):
        editor.test_button.click()
    editor.show_test_result("blood e", store.get("bloodletter_e"))
    assert editor.test_label.text() == 'Heard: "blood e" → ✓ matches Bloodletter E'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_editor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pvptimer.editor'`.

- [ ] **Step 3: Implement `src/pvptimer/editor.py`**

```python
"""Ability editor window: list, add, edit, delete, import/export and test voice phrases."""
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .abilities import MAX_COOLDOWN_S, SLOTS, Ability
from .store import AbilityStore

COLUMNS = ("Name", "Slot", "Cooldown", "Voice phrases", "Status")
STATUS_COLUMN = 4
TEST_TIMEOUT_MS = 10_000
UnknownWords = Callable[[Iterable[str]], set[str]]


def ability_status(ability: Ability, unknown_words: UnknownWords, duplicates: set[str]) -> tuple[str, str]:
    """(Status column text, tooltip)."""
    words = unknown_words(ability.phrases)
    if words:
        return ("⚠ word", "Not in the speech model's vocabulary: " + ", ".join(sorted(words))
                + ". Respell with common words (e.g. 'hell ion').")
    dups = sorted(set(ability.phrases) & duplicates)
    if dups:
        return "⚠ dup", "Also used by another ability: " + ", ".join(dups)
    return "✓", ""


def describe_test_result(text: str, matched: Ability | None, editing_id: str, dirty: bool) -> str:
    if not text:
        message = "Heard nothing — try again."
    elif matched is None:
        message = f'Heard: "{text}" → ✗ no match'
    elif matched.id == editing_id:
        message = f'Heard: "{text}" → ✓ matches {matched.name}'
    else:
        message = f'Heard: "{text}" → matches a different ability: {matched.name}'
    if dirty:
        message += "  (unsaved changes can't be heard until you Save)"
    return message


class EditorWindow(QWidget):
    test_requested = Signal()

    def __init__(self, store: AbilityStore, unknown_words: UnknownWords) -> None:
        super().__init__()
        self.setWindowTitle("PVPTimer – Ability Editor")
        self.resize(780, 600)
        self._store = store
        self._unknown_words = unknown_words
        self._editing: Ability | None = None  # None = a new, unsaved ability

        # toolbar
        self.add_button = QPushButton("+ Add")
        self.delete_button = QPushButton("Delete")
        self.import_button = QPushButton("Import…")
        self.export_button = QPushButton("Export…")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search names and phrases")
        toolbar = QHBoxLayout()
        for widget in (self.add_button, self.delete_button, self.import_button, self.export_button):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        toolbar.addWidget(self.search_edit)

        # table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        # form
        self.form_title = QLabel()
        self.name_edit = QLineEdit()
        self.slot_combo = QComboBox()
        self.slot_combo.addItems(SLOTS)
        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.1, MAX_COOLDOWN_S)
        self.cooldown_spin.setDecimals(1)
        self.cooldown_spin.setSuffix(" s")
        self.phrases_edit = QPlainTextEdit()
        self.phrases_edit.setPlaceholderText("One phrase per line, e.g.\nblood letter e\nblood e")
        self.phrases_edit.setFixedHeight(90)
        self.errors_label = QLabel()
        self.errors_label.setStyleSheet("color: #dc2626;")
        self.errors_label.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Slot", self.slot_combo)
        form.addRow("Cooldown", self.cooldown_spin)
        form.addRow("Phrases", self.phrases_edit)
        form.addRow(self.errors_label)

        self.test_button = QPushButton("🎤 Test phrase")
        self.test_label = QLabel()
        self.test_label.setWordWrap(True)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_label, 1)

        self.save_button = QPushButton("Save")
        self.revert_button = QPushButton("Revert")
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        buttons_row.addWidget(self.save_button)
        buttons_row.addWidget(self.revert_button)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.form_title)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addLayout(buttons_row)

        self._test_timeout = QTimer(self)
        self._test_timeout.setSingleShot(True)
        self._test_timeout.setInterval(TEST_TIMEOUT_MS)
        self._test_timeout.timeout.connect(self._on_test_timeout)

        self.add_button.clicked.connect(self._add)
        self.delete_button.clicked.connect(self._delete)
        self.import_button.clicked.connect(self._import)
        self.export_button.clicked.connect(self._export)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.name_edit.textChanged.connect(lambda *_: self._validate_form())
        self.phrases_edit.textChanged.connect(lambda *_: self._validate_form())
        self.slot_combo.currentIndexChanged.connect(lambda *_: self._validate_form())
        self.cooldown_spin.valueChanged.connect(lambda *_: self._validate_form())
        self.save_button.clicked.connect(self._save)
        self.revert_button.clicked.connect(self._revert)
        self.test_button.clicked.connect(self._request_test)
        store.abilities_changed.connect(self.refresh)

        self.refresh()
        self._load_form(None)

    # table --------------------------------------------------------------
    def refresh(self) -> None:
        abilities = self._store.abilities()
        duplicates = self._store.duplicate_phrases()
        self.table.blockSignals(True)
        self.table.setRowCount(len(abilities))
        for row, ability in enumerate(abilities):
            status, tip = ability_status(ability, self._unknown_words, duplicates)
            cells = (ability.name, ability.slot, f"{ability.cooldown_s:.1f} s", ", ".join(ability.phrases), status)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, ability.id)
                if col == STATUS_COLUMN:
                    item.setToolTip(tip)
                self.table.setItem(row, col, item)
        self._select_row_for(self._editing.id if self._editing else None)
        self.table.blockSignals(False)
        self._apply_filter(self.search_edit.text())
        if self._editing is not None and self._store.get(self._editing.id) is None:
            self._load_form(None)

    def _select_row_for(self, ability_id: str | None) -> None:
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == ability_id:
                self.table.selectRow(row)
                return

    def _apply_filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for row in range(self.table.rowCount()):
            haystack = f"{self.table.item(row, 0).text()} {self.table.item(row, 3).text()}".casefold()
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _on_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            ability_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
            self._load_form(self._store.get(ability_id))

    # form ---------------------------------------------------------------
    def form_ability(self) -> Ability:
        return Ability(
            id=self._editing.id if self._editing else "",
            name=self.name_edit.text(),
            slot=self.slot_combo.currentText(),
            cooldown_s=round(self.cooldown_spin.value(), 1),
            phrases=tuple(self.phrases_edit.toPlainText().splitlines()),
        )

    def is_dirty(self) -> bool:
        current = self.form_ability().normalized()
        if self._editing is None:
            return bool(current.name or current.phrases)
        return current != self._editing

    def _load_form(self, ability: Ability | None) -> None:
        self._editing = ability
        widgets = (self.name_edit, self.slot_combo, self.cooldown_spin, self.phrases_edit)
        for widget in widgets:
            widget.blockSignals(True)
        self.name_edit.setText(ability.name if ability else "")
        self.slot_combo.setCurrentText(ability.slot if ability else "E")
        self.cooldown_spin.setValue(ability.cooldown_s if ability else 10.0)
        self.phrases_edit.setPlainText("\n".join(ability.phrases) if ability else "")
        for widget in widgets:
            widget.blockSignals(False)
        self.form_title.setText(f"Edit: {ability.name}" if ability else "New ability")
        self.delete_button.setEnabled(ability is not None)
        self._test_timeout.stop()
        self.test_label.setText("")
        self._validate_form()

    def _validate_form(self) -> None:
        dirty = self.is_dirty()
        errors = self._store.validate(self.form_ability()) if dirty else []
        self.errors_label.setText("\n".join(errors))
        self.save_button.setEnabled(dirty and not errors)
        self.revert_button.setEnabled(dirty)

    def _save(self) -> None:
        try:
            stored = self._store.upsert(self.form_ability())
        except ValueError as exc:
            self.errors_label.setText(str(exc))
            return
        self._editing = stored
        self.refresh()
        self._load_form(stored)

    def _revert(self) -> None:
        self._load_form(self._editing)

    def _add(self) -> None:
        self.table.clearSelection()
        self._load_form(None)
        self.name_edit.setFocus()

    def _delete(self) -> None:
        if self._editing is None:
            return
        answer = QMessageBox.question(self, "Delete ability", f"Delete '{self._editing.name}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._store.delete(self._editing.id)
        self._load_form(None)

    # import / export ----------------------------------------------------
    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import abilities", "", "Ability lists (*.json)")
        if not path:
            return
        try:
            result = self._store.import_file(Path(path), self._ask_replace)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, "Import failed", f"Could not import {Path(path).name}: {exc}")
            return
        lines = [f"Added: {len(result.added)}", f"Replaced: {len(result.replaced)}",
                 f"Kept existing: {len(result.kept)}"]
        if result.skipped:
            lines.append("Skipped:\n  " + "\n  ".join(result.skipped))
        QMessageBox.information(self, "Import finished", "\n".join(lines))

    def _ask_replace(self, existing: Ability, incoming: Ability) -> bool:
        answer = QMessageBox.question(
            self, "Ability already exists",
            f"'{existing.name}' already exists. Replace it with the imported version "
            f"({incoming.cooldown_s:g} s: {', '.join(incoming.phrases)})?")
        return answer == QMessageBox.StandardButton.Yes

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export abilities", "pvptimer-abilities.json",
                                              "Ability lists (*.json)")
        if not path:
            return
        try:
            self._store.export_file(Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not write {path}: {exc}")

    # phrase test ----------------------------------------------------------
    def _request_test(self) -> None:
        self.test_label.setText("Hold your push-to-talk key and speak…")
        self._test_timeout.start()
        self.test_requested.emit()

    def show_test_result(self, text: str, matched: Ability | None) -> None:
        if not self._test_timeout.isActive():
            return  # not waiting for a test result
        self._test_timeout.stop()
        editing_id = self._editing.id if self._editing else ""
        self.test_label.setText(describe_test_result(text, matched, editing_id, self.is_dirty()))

    def _on_test_timeout(self) -> None:
        self.test_label.setText("No speech heard within 10 seconds.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_editor.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/pvptimer/editor.py tests/test_editor.py
git commit -m "feat: ability editor with validation, vocabulary status, import/export and phrase test" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Full application wiring (voice → timer end-to-end)

**Files:**
- Replace: `src/pvptimer/app.py` (the whole file)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: every earlier module, using the exact names listed in their Interfaces blocks.
- Produces: `PvpTimerApp(qapp)` with attributes `settings`, `store`, `timers`, `overlay`, `beep`, `ptt`, `speech`, `editor`, `tray`; methods `open_editor()`, `open_settings()`, `shutdown()`, `quit()`; internal entry points used by tests: `_on_recognized(text)`, `_arm_test()`, `_apply_settings(Settings)`. Also `main() -> int`.

- [ ] **Step 1: Write the failing test `tests/test_app.py`**

```python
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication

from pvptimer import app as app_module
from pvptimer import paths
from pvptimer.settings import load_settings


@pytest.fixture
def notes(monkeypatch):
    messages = []
    monkeypatch.setattr(app_module.PvpTimerApp, "_notify", lambda self, message: messages.append(message))
    return messages


@pytest.fixture
def running_app(qtbot, tmp_path, monkeypatch, make_ability, notes):
    monkeypatch.setattr(app_module.paths, "model_dir", lambda *a: tmp_path / "no-model")
    monkeypatch.setattr(app_module.PvpTimerApp, "open_settings", lambda self: None)
    application = app_module.PvpTimerApp(QApplication.instance())
    application.store.upsert(make_ability())
    yield application
    application.shutdown()


def test_missing_model_is_reported(running_app, notes, qtbot):
    qtbot.waitUntil(lambda: any("Speech model not found" in m for m in notes), timeout=3000)


def test_recognized_phrase_starts_and_clears_timers(running_app):
    running_app._on_recognized("blood letter e")
    assert [v.ability_id for v in running_app.timers.snapshot()] == ["bloodletter_e"]
    running_app._on_recognized("clear blood letter e")
    assert running_app.timers.snapshot() == []
    running_app._on_recognized("blood letter e")
    running_app._on_recognized("clear all")
    assert running_app.timers.snapshot() == []


def test_unmatched_phrase_is_shown_on_overlay(running_app, monkeypatch):
    heard = []
    monkeypatch.setattr(running_app.overlay, "show_heard", heard.append)
    running_app._on_recognized("hello")
    running_app._on_recognized("")
    assert heard == ["hello", ""]


def test_armed_test_routes_next_result_to_editor_only(running_app, monkeypatch):
    running_app.open_editor()
    results = []
    monkeypatch.setattr(running_app.editor, "show_test_result",
                        lambda text, ability: results.append((text, ability.id)))
    running_app._arm_test()
    running_app._on_recognized("blood letter e")
    assert results == [("blood letter e", "bloodletter_e")]
    assert running_app.timers.snapshot() == []
    running_app._on_recognized("blood letter e")  # test window used up: back to normal
    assert len(running_app.timers.snapshot()) == 1


def test_applying_settings_updates_components_and_saves(running_app):
    running_app._apply_settings(replace(running_app.settings, speech_offset_s=1.5, warning_s=5.0))
    assert running_app.timers.speech_offset_s == 1.5
    assert running_app.timers.warning_s == 5.0
    saved, _ = load_settings(paths.app_data_dir() / "settings.json")
    assert saved.speech_offset_s == 1.5
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -v`
Expected: FAIL. `AttributeError` (no `store`, `_on_recognized`, `open_settings` …) on the skeleton app.

- [ ] **Step 3: Replace `src/pvptimer/app.py` with the full wiring**

```python
"""Application wiring: tray icon, overlay, timers, push-to-talk, speech, editor and settings."""
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from types import SimpleNamespace

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import paths
from .beep import ReadyBeep
from .editor import EditorWindow
from .hotkey import PttListener
from .overlay import OverlayWindow
from .router import Action, decide
from .settings import Settings, load_settings, save_settings
from .settings_dialog import SettingsDialog
from .speech import SpeechWorker, input_device_names
from .store import AbilityStore
from .timers import TimerManager

TICK_MS = 66  # ~15 fps
TEST_WINDOW_S = 10.0
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

        self.editor: EditorWindow | None = None
        self._test_deadline = 0.0
        self._settings_open = False

        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip("PVPTimer")
        self.tray.setContextMenu(self._build_menu())
        self.tray.show()

        self._tick = QTimer(self)
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        self.overlay.show()
        self._push_phrases()
        self._speech_thread.start()
        self.ptt.start(s.ptt)

        for warning in [settings_warning, *self.store.warnings]:
            if warning:
                self._notify(warning)
        if s.ptt is None:
            QTimer.singleShot(0, self.open_settings)  # first run: ask for the push-to-talk key

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("Editor", self.open_editor)
        self._move_action = QAction("Move overlay", menu, checkable=True)
        self._move_action.toggled.connect(self.overlay.set_move_mode)
        menu.addAction(self._move_action)
        menu.addAction("Settings", self.open_settings)
        menu.addSeparator()
        menu.addAction("Debug: fire test timer", lambda: self.timers.start(DEBUG_ABILITY))
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._menu = menu
        return menu

    # runtime ------------------------------------------------------------
    def _on_tick(self) -> None:
        if self.timers.ready_events():  # before overlay paints, which calls snapshot()
            self.beep.play()
        self.overlay.update()

    def _push_phrases(self) -> None:
        self.phrases_changed.emit(self.store.phrases())

    def _on_recognized(self, text: str) -> None:
        test_mode = time.monotonic() < self._test_deadline
        self._test_deadline = 0.0
        decision = decide(text, self.store.match, test_mode)
        log.info("heard %r -> %s", decision.text, decision.action.value)
        if decision.action is Action.TEST_RESULT:
            if self.editor is not None:
                self.editor.show_test_result(decision.text, decision.ability)
        elif decision.action is Action.CLEAR_ALL:
            self.timers.clear_all()
        elif decision.action is Action.CLEAR:
            self.timers.clear(decision.ability.id)
        elif decision.action is Action.START:
            self.timers.start(decision.ability)
        else:
            self.overlay.show_heard(decision.text)

    def _on_model_ready(self) -> None:
        flagged = [a.name for a in self.store.abilities() if self.speech.unknown_words(a.phrases)]
        if flagged:
            self._notify(f"{len(flagged)} abilities have phrases with unrecognized words "
                         f"({', '.join(flagged[:5])}). Open the Editor to respell them.")
        self._push_phrases()  # rebuild the grammar now that the vocabulary is known
        if self.editor is not None:
            self.editor.refresh()

    def _notify(self, message: str) -> None:
        log.warning(message)
        self.tray.showMessage("PVPTimer", message, QSystemTrayIcon.MessageIcon.Warning, 6000)

    def _on_ptt_failed(self, message: str) -> None:
        self._notify(message)
        self.open_settings()

    def _save_overlay_position(self, screen: int, x: int, y: int) -> None:
        overlay = self.settings.overlay
        overlay.screen, overlay.x, overlay.y = screen, x, y
        save_settings(self._settings_path, self.settings)

    # windows ------------------------------------------------------------
    def open_editor(self) -> None:
        if self.editor is None:
            self.editor = EditorWindow(self.store, self.speech.unknown_words)
            self.editor.test_requested.connect(self._arm_test)
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()

    def _arm_test(self) -> None:
        self._test_deadline = time.monotonic() + TEST_WINDOW_S

    def open_settings(self) -> None:
        if self._settings_open:
            return
        self._settings_open = True
        try:
            import sounddevice as sd
            try:
                devices = input_device_names(list(sd.query_devices()))
            except Exception as exc:
                log.warning("could not list audio devices: %s", exc)
                devices = []
            dialog = SettingsDialog(self.settings, devices, self.ptt)
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
        self._tick.stop()
        self.ptt.cancel_capture()
        self.ptt.stop()
        self._speech_thread.quit()
        self._speech_thread.wait(2000)
        self.speech.stop()
        if self.editor is not None:
            self.editor.close()
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest -v`
Expected: the whole suite passes.

- [ ] **Step 5: HUMAN STEP: end-to-end voice check**

Ask the user to run `.venv/Scripts/python -m pvptimer` and do the following:
1. First run: the Settings dialog opens. Click the push-to-talk button and press their key or mouse side button. OK is now enabled; click it.
2. Tray → **Editor** → **+ Add**: `Bloodletter E`, slot E, cooldown 15, phrases `blood letter e` / `blood e` → **Save**. The Status column shows ✓ (or ⚠ word, then respell).
3. **Test phrase**, then hold push-to-talk and say "blood e". The editor shows `Heard: "blood e" → ✓ matches Bloodletter E`.
4. Close the editor. Hold push-to-talk and say "blood letter e": a timer appears within about 1 s of release. Say it again and the timer restarts. Say "clear all" and it disappears. Say gibberish and "? heard: …" flashes.
5. Repeat step 4 in-game (borderless) while Discord is open with the same push-to-talk key.

Check `%APPDATA%\PVPTimer\pvptimer.log` for warnings and fix anything reported before continuing.

- [ ] **Step 6: Commit**

```bash
git add src/pvptimer/app.py tests/test_app.py
git commit -m "feat: wire speech, push-to-talk, editor and settings into the tray app" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Packaging and README

**Files:**
- Create: `pvptimer.spec`, `README.md`
- Modify: `.gitignore` (add `*.zip`)

**Interfaces:**
- Consumes: `paths.MODEL_NAME` (it must match `MODEL` in the spec file, including any change made in Task 2), and `src/pvptimer/__main__.py` as the entry point.
- Produces: `dist/PVPTimer/PVPTimer.exe` and `dist/PVPTimer-0.1.0.zip`.

- [ ] **Step 1: Write `pvptimer.spec`**

```python
# PyInstaller build:  .venv/Scripts/pyinstaller pvptimer.spec --noconfirm
# MODEL must equal pvptimer.paths.MODEL_NAME.
from PyInstaller.utils.hooks import collect_dynamic_libs

MODEL = "vosk-model-small-en-us-0.15"

a = Analysis(
    ["src/pvptimer/__main__.py"],
    pathex=["src"],
    binaries=collect_dynamic_libs("vosk"),
    datas=[
        ("src/pvptimer/data", "pvptimer/data"),
        (f"models/{MODEL}", f"models/{MODEL}"),
    ],
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PVPTimer", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="PVPTimer", upx=False)
```

- [ ] **Step 2: Build**

Run:
```bash
.venv/Scripts/python -c "from pvptimer.paths import MODEL_NAME; print(MODEL_NAME)"
.venv/Scripts/pyinstaller pvptimer.spec --noconfirm
ls dist/PVPTimer/PVPTimer.exe dist/PVPTimer/_internal/models dist/PVPTimer/_internal/pvptimer/data
```
Expected: the printed model name matches `MODEL` in the spec. The build ends with `Build complete!`. The `ls` shows the exe, the model folder, and `default_abilities.json` + `ready.wav`.

- [ ] **Step 3: Smoke-test the build with an isolated home**

Run:
```bash
PVPTIMER_HOME="$(pwd)/build/smoke-home" ./dist/PVPTimer/PVPTimer.exe &
```
Expected: the tray icon appears and the Settings dialog opens. Bind a key, use **Debug: fire test timer**, then use **Quit**. Then:
```bash
cat build/smoke-home/pvptimer.log
```
Expected: the log has no `Speech model not found`, no `CRITICAL` lines, and no `unhandled exception`.

- [ ] **Step 4: Write `README.md`**

````markdown
# PVPTimer

Voice-triggered enemy cooldown timers for Albion Online. Hold your push-to-talk key, say
what the enemy just used ("blood letter e"), and a countdown appears on a transparent
overlay above the game.

PVPTimer never reads game memory, injects into the game, or inspects network traffic.
It only listens to your microphone while push-to-talk is held and draws a window on top
of your screen.

## Using it

1. Unzip `PVPTimer-x.y.z.zip` anywhere and run `PVPTimer.exe`. It lives in the system tray.
2. On first run, pick your push-to-talk key or mouse side button. Using the same key as
   Discord works well: your callout to the team also starts the timer.
3. Tray → **Editor** to add abilities: a name, slot, cooldown in seconds, and one or more
   phrases you'll say. Use **Test phrase** to check how the app hears you.
4. Run Albion in **borderless fullscreen** or **windowed** mode. Exclusive fullscreen hides
   the overlay (the ready beep still plays).
5. Tray → **Move overlay** to drag the timers where you want them.

Voice commands: any saved phrase starts or restarts that ability's timer.
`clear <phrase>` removes one timer. `clear all` removes every timer.

### Tips

- A ⚠ word status means the speech model doesn't know a word (often Albion names).
  Respell it with common words: `hellion` → `hell ion`.
- Single letters are easy to mishear. Add a few variants per ability ("blood e",
  "blood letter e").
- If push-to-talk never fires while in game, check that Albion is not running as
  administrator. Windows blocks non-admin apps from seeing keys pressed in admin windows.
- Some antivirus tools flag new unsigned executables. The source is in this repository.

### Files

Your abilities, settings and log are in `%APPDATA%\PVPTimer\`. Export/Import in the
editor shares ability lists as JSON.

## Development

```bash
"$LOCALAPPDATA/Programs/Python/Python313/python.exe" -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python scripts/get_model.py
.venv/Scripts/python -m pytest
.venv/Scripts/python -m pvptimer
```

To ship your ability list as the default for everyone: Editor → **Export…**, save the
file over `src/pvptimer/data/default_abilities.json`, then rebuild.

### Building a release

```bash
.venv/Scripts/pyinstaller pvptimer.spec --noconfirm
powershell -NoProfile -Command "Compress-Archive -Force dist/PVPTimer dist/PVPTimer-0.1.0.zip"
```
````

- [ ] **Step 5: Zip the release**

Run:
```bash
printf '*.zip\n' >> .gitignore
powershell -NoProfile -Command "Compress-Archive -Force dist/PVPTimer dist/PVPTimer-0.1.0.zip"
ls -la dist/PVPTimer-0.1.0.zip
```
Expected: the zip exists, around 100–150 MB.

- [ ] **Step 6: HUMAN STEP: clean-machine check**

Ask the user to copy the zip to another Windows account or PC with no Python installed, unzip it, run `PVPTimer.exe`, and repeat the Task 13 Step 5 checks 1–4.

- [ ] **Step 7: Run the full suite, then commit**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all passed.

```bash
git add pvptimer.spec README.md .gitignore
git commit -m "build: PyInstaller one-folder packaging and README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
