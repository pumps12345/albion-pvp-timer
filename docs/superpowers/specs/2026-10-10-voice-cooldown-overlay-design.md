# PVPTimer — Voice-Triggered Enemy Cooldown Overlay

**Date:** 2026-10-10
**Status:** Approved for initial build

## 1. Purpose

A local Windows utility for Albion Online PvP. While holding a push-to-talk key, the player speaks a short phrase naming an enemy ability they just saw used (e.g. "blood letter e", "cleric robe r"). The app recognizes the phrase offline with Vosk, looks up the ability's cooldown in a local database, and shows a countdown bar on a transparent overlay above the game, so the player knows when that enemy ability is likely available again.

The app never reads game memory, injects into the game process, or inspects network traffic. It is a voice-controlled stopwatch drawn over the screen.

### Success criteria

- A recognized phrase produces a visible timer within ~1 s of releasing the push-to-talk key.
- Curated phrases are recognized correctly ≥ 90% of the time on the user's microphone (measured in the spike, §11).
- The overlay never takes focus or captures mouse clicks from the game.
- An ability added in the editor works in the next fight without restarting the app.
- The app can be zipped and handed to another player, who can run it without installing Python.

### Decisions made during brainstorming

| Topic | Decision |
|---|---|
| Whose cooldowns | Enemy abilities |
| Mic activation | Push-to-talk (global key or mouse button; sharing the Discord PTT key is encouraged) |
| Display mode | Borderless fullscreen / windowed supported. Exclusive fullscreen is not supported (overlay hidden); beep still works |
| Repeat call of a running ability | Restarts that ability's timer (one timer per ability) |
| On ready | Warning color before ready, then READY flash + beep, then fade out |
| Database entry | Through an in-app editor UI; JSON on disk; defaults bundled for distribution |
| Content focus | Small-scale / open world, Corrupted Dungeons / Hellgates |
| Stack | Python 3.13, PySide6, Vosk |

## 2. Non-goals (v1)

- Tracking multiple enemies with the same ability separately.
- Calculating cooldown reduction from enemy gear or buffs.
- Importing ability data from game files (ao-bin-dumps).
- Item icons on the overlay.
- Detecting exclusive fullscreen mode (documented in the README instead).
- Tracking the player's own cooldowns.
- Spoken (TTS) alerts.

## 3. Architecture

```
 pynput listener ──ptt_down/ptt_up──┐
                                    ▼
 Microphone ──sounddevice──► audio queue ──► SpeechWorker (QThread, Vosk + grammar)
                                                    │ recognized(text, ability_id | None)
                                                    ▼
                                             app.py (router)
                                   ┌────────────────┴────────────────┐
                                   ▼                                 ▼
                         TimerManager (timers.py)          Editor "Test phrase" panel
                                   │
                                   ▼
                         Overlay (redraws ~15 fps)

 AbilityStore (store.py) ── abilities_changed ──► SpeechWorker rebuilds its grammar
```

Threads: the pynput listener and the sounddevice callback run on their own threads. Vosk runs in one `QThread` worker. Every UI and timer state change happens on the Qt main thread, and other threads reach it only through Qt signals.

## 4. Data model

### 4.1 Ability

```json
{
  "id": "bloodletter_e",
  "name": "Bloodletter E",
  "slot": "E",
  "cooldown_s": 15.0,
  "phrases": ["blood letter e", "blood e"]
}
```

| Field | Rules |
|---|---|
| `id` | Unique. Generated from `name` when the ability is created (lowercase, non-alphanumerics → `_`, `_2` etc. added on collision). Never changes after creation. |
| `name` | Display name, non-empty. |
| `slot` | One of `Q`, `W`, `E`, `R`, `D`, `F`, `Passive`. Informational only. |
| `cooldown_s` | Number > 0, up to 600. |
| `phrases` | ≥ 1 entry. Normalized on save: lowercase, punctuation removed, whitespace collapsed. A phrase may not belong to more than one ability. The word `clear` is reserved and may not start a phrase (it is the command prefix). |

Cooldown values come from the user through the editor. This spec does not assume any cooldown data.

### 4.2 Files

| File | Location | Writable | Contents |
|---|---|---|---|
| Defaults | Bundled: `src/pvptimer/data/default_abilities.json` | No (in the app) | `{"version": 1, "abilities": [...]}` |
| User list | `%APPDATA%\PVPTimer\abilities.json` | Yes | `{"version": 1, "abilities": [...], "deleted_ids": [...]}` |
| Settings | `%APPDATA%\PVPTimer\settings.json` | Yes | See §4.3 |

**Combining the lists:** effective list = defaults, with any user ability of the same `id` replacing the default, user-only abilities added, and any `id` in `deleted_ids` removed. Edits in the editor write to the user file only, so editing or deleting a default ability does not change the bundled file.

**Saving:** write to `*.tmp`, then rename over the target, so a crash mid-write never corrupts the file.

**Promoting to defaults:** "Export…" writes the effective list as a defaults-format file. The maintainer copies that file to `default_abilities.json` before building a release.

**Import:** reads a defaults-format file and adds its abilities to the user list. If an `id` already exists, a dialog asks whether to keep the existing one or replace it.

### 4.3 Settings

```json
{
  "version": 1,
  "ptt": {"device": "mouse", "button": "x1"},
  "mic_device": null,
  "speech_offset_s": 0.7,
  "warning_s": 3.0,
  "ready_display_s": 3.0,
  "beep_enabled": true,
  "beep_volume": 0.6,
  "overlay": {"screen": 0, "x": 40, "y": 200, "opacity": 0.9}
}
```

- `ptt`: either `{"device": "keyboard", "key": "<pynput key name>"}` or `{"device": "mouse", "button": "x1" | "x2" | "middle"}`. There is no default key: on first run `ptt` is `null`, and the Settings dialog opens and asks the user to press their key. (The example above shows a file after the user has bound one.)
- `mic_device`: a sounddevice input device name; `null` means the system default.
- `speech_offset_s`: subtracted from the start time to make up for the delay between the enemy casting and the player speaking.

## 5. Components

Package: `src/pvptimer/`. Each module has one job and can be tested on its own.

### 5.1 `paths.py`
Finds the bundled data folder (works both from source and from the PyInstaller build via `sys._MEIPASS`), the Vosk model folder, and `%APPDATA%\PVPTimer` (created if missing).

### 5.2 `store.py` — `AbilityStore` (QObject)
- `load()`: reads the defaults and user files and combines them (§4.2).
- `abilities() -> list[Ability]`, `get(id)`, `match(text) -> Ability | None` (exact match on the normalized phrase).
- `upsert(ability)`, `delete(id)`, `import_file(path)`, `export_file(path)`.
- `validate(ability) -> list[str]`: lists every problem (empty name, cooldown out of range, a phrase used by another ability, a reserved word).
- Emits `abilities_changed` after every change.
- Plain JSON and dataclasses; the matching and validation logic doesn't touch Qt.

### 5.3 `timers.py` — `TimerManager`
- Takes `clock: Callable[[], float]` (default `time.monotonic`) when created.
- `start(ability)`: sets `end = clock() - speech_offset_s + cooldown_s`. If the ability already has a timer, it is replaced (restart).
- `clear(ability_id)`, `clear_all()`.
- `snapshot() -> list[TimerView]`, sorted by time remaining, where each view has `ability_id, name, remaining_s, fraction, state`.
- States: `running` (remaining > `warning_s`), `warning` (0 < remaining ≤ `warning_s`), `ready` (remaining ≤ 0 and less than `ready_display_s` since reaching zero), and removed after that.
- `ready_events()` returns the abilities that became ready since the last call, which the app uses to fire the beep exactly once.
- No Qt imports.

### 5.4 `hotkey.py` — `PttListener` (QObject)
- Wraps a `pynput` keyboard listener or mouse listener depending on the settings.
- Emits `ptt_down` and `ptt_up` only on state changes, so the key repeating while held is ignored.
- `rebind(binding)` swaps the listener while the app is running.
- `capture_next()`: used by the Settings dialog to record the next key or button the user presses.

### 5.5 `speech.py` — `SpeechWorker` (QObject moved to a QThread)
- Loads the Vosk model once at startup. Default model: `vosk-model-small-en-us-0.15`.
- The **grammar** is built from every ability phrase, plus `"clear all"`, plus `"clear " + phrase` for each phrase, plus `"[unk]"`. It is rebuilt (by creating a new `KaldiRecognizer`) whenever `abilities_changed` fires.
- The sounddevice `RawInputStream` (16 kHz, mono, int16) stays open the whole time. While PTT is held, the audio callback puts blocks in a queue and the worker passes them to `AcceptWaveform`. Audio outside PTT is thrown away.
- On `ptt_up`: process the rest of the queue, call `FinalResult()`, normalize the text, and emit `recognized(text: str)`. Then `Reset()`.
- `unknown_words(phrases) -> set[str]`: words the model can't recognize. How to detect them is decided in the spike (§11).

### 5.6 Router (in `app.py`)
When `recognized(text)` arrives:
1. If the editor's Test panel is waiting for a result, send the text there only and stop.
2. `"clear all"` → `timers.clear_all()`.
3. `"clear <phrase>"` → clear that phrase's ability.
4. `store.match(text)` → `timers.start(ability)`.
5. Empty text, `[unk]` or no match → `overlay.show_heard(text)`, which shows a "? heard: …" line for 1.5 s.

### 5.7 `overlay.py` — `OverlayWindow`
- Window settings: `FramelessWindowHint | WindowStaysOnTopHint | Tool | WindowTransparentForInput | WindowDoesNotAcceptFocus`, with `WA_TranslucentBackground` and `WA_ShowWithoutActivating`.
- A `QTimer` redraws at ~15 fps from `timers.snapshot()`. Each row is about 260 × 26 px: the name, the time remaining (one decimal place under 10 s, whole seconds above), and a bar that shrinks as time runs out.
- Colors: `running` neutral (slate), `warning` amber, `ready` green, pulsing for `ready_display_s` and then fading out.
- **Move mode** (turned on and off from the tray): the window accepts mouse input, shows a dashed border and a sample row, and can be dragged. Leaving move mode saves `overlay.screen/x/y` and makes the window click-through again.
- When there are no timers the window draws nothing; it stays open to avoid flicker.

### 5.8 Audio cue
A bundled `ready.wav` played through `QSoundEffect` at `beep_volume`, once for each `ready_events()` entry, if `beep_enabled`.

### 5.9 `editor.py` — `EditorWindow`

```
┌─ PVPTimer – Ability Editor ───────────────────────────────────────────┐
│ [+ Add]  [Delete]  [Import…]  [Export…]           Search: [blood   ]  │
├───────────────────┬──────┬──────────┬────────────────────────┬────────┤
│ Name              │ Slot │ Cooldown │ Voice phrases          │ Status │
├───────────────────┼──────┼──────────┼────────────────────────┼────────┤
│ Bloodletter E     │  E   │  15.0 s  │ blood letter e, blood e│   ✓    │
│ Cleric Robe R     │  R   │  30.0 s  │ cleric robe r, robe r  │   ✓    │
│ Hellion Hood D    │  D   │  25.0 s  │ hellion d              │ ⚠ word │
└───────────────────┴──────┴──────────┴────────────────────────┴────────┘
┌─ Edit: Bloodletter E ─────────────────────────────────────────────────┐
│ Name:     [Bloodletter E        ]   Slot: [E ▾]   Cooldown: [15.0] s  │
│ Phrases:  [blood letter e] [x]                                        │
│           [blood e       ] [x]   [+ phrase]                           │
│                                                                       │
│ [🎤 Test phrase]  Hold your push-to-talk key and speak…               │
│   Heard: "blood e"  →  ✓ matches Bloodletter E                        │
│                                                       [Save] [Cancel] │
└───────────────────────────────────────────────────────────────────────┘
```

(The cooldown values in the mock-up are only placeholders.)

- The table is a `QTableView` over a model built from the store, with a search box that filters it.
- **Status column:** `✓`, `⚠ word` (contains a word the model doesn't know; the tooltip lists them), or `⚠ dup` (phrase shared with another ability, which validation normally prevents).
- **The edit form** checks `store.validate()` as you type. Save is disabled while there are errors, and each error is shown next to its field.
- **Test phrase** puts the router into test mode (§5.6, step 1). The next result is shown as `Heard: "<text>" → ✓ matches <name>`, `→ ✗ no match`, or `→ matches a different ability: <name>`. Test mode turns off after one result or after 10 s.
- Save calls `store.upsert()`, which emits `abilities_changed`, which makes the speech worker rebuild its grammar.

### 5.10 `settings.py` — `Settings` + `SettingsDialog`
Loads and saves `settings.json` and edits every field in §4.3: PTT key (a "Press a key…" capture button), microphone (dropdown of input devices), speech offset, warning seconds, ready display seconds, beep on/off and volume, and overlay opacity.

### 5.11 `app.py`
Creates the `QApplication` and a `QSystemTrayIcon` with this menu: **Editor**, **Move overlay** (on/off), **Settings**, **Debug: fire test timer**, **Quit**. It creates and connects all the components above. Entry point: `python -m pvptimer`.

## 6. Error handling

| Condition | Behavior |
|---|---|
| Vosk model folder missing or unreadable | Tray notification explains it; speech is disabled; the editor and overlay still work. |
| No input device, or the chosen mic is gone | Tray notification; falls back to the system default; if that fails too, speech is disabled. |
| pynput listener fails to start | Tray notification; the Settings dialog opens so the user can pick another key. |
| Corrupt user or settings JSON | The bad file is renamed to `*.bad-<timestamp>`, defaults are loaded, and a tray notification says so. |
| Phrases with unknown words | Flagged in the editor; a startup notification counts them ("3 phrases contain unrecognized words"). |
| Recognition produced no match | `show_heard` on the overlay (§5.6, step 5). |

Errors are logged to `%APPDATA%\PVPTimer\pvptimer.log` (rotating, 1 MB × 3).

## 7. Testing

- **Unit tests (`pytest`):**
  - `timers.py`: state changes at the exact boundaries, restart replaces the old timer, the offset is applied, `ready_events` fires once, clear and clear-all, sort order. All with a fake clock.
  - `store.py`: combining the lists (user replaces default, deleted ids, user-only abilities), phrase normalization, validation rules, `match()`, import conflicts, safe-save behavior, recovery from corrupt files (using `tmp_path`).
  - Router logic: test mode, clear commands, the no-match path. Tested by making the routing decision a plain function separate from Qt.
- **Speech:** checked in the spike (§11) and afterwards with the editor's Test phrase button. No automated tests.
- **Overlay and push-to-talk:** a manual checklist run in-game in borderless mode: no focus stealing, clicks pass through, move mode works, position survives a restart, colors and beep at the right moments.

## 8. Project layout

```
PVPTimer/
  pyproject.toml            # deps: PySide6, vosk, sounddevice, pynput; dev: pytest, pyinstaller
  README.md                 # setup, model download, borderless requirement
  src/pvptimer/
    __init__.py  __main__.py  app.py  paths.py  settings.py
    store.py  timers.py  hotkey.py  speech.py  overlay.py  editor.py
    data/default_abilities.json  data/ready.wav
  models/                   # Vosk model, gitignored; fetched by scripts/get_model.py
  scripts/get_model.py
  tests/
  spike/                    # throwaway recognition test (§11)
  pvptimer.spec             # PyInstaller config
  docs/superpowers/specs/
```

## 9. Packaging and distribution

- PyInstaller in one-folder mode (not one-file, which starts slower and is more often flagged by antivirus). It must include: the `vosk` native DLLs (via `collect_dynamic_libs("vosk")`), `pvptimer/data/*`, and the `models/vosk-model-small-en-us-0.15` folder.
- The result is a `PVPTimer/` folder with `PVPTimer.exe`, zipped for sharing (expected size ~100–150 MB).
- On first run on a new machine, the app creates `%APPDATA%\PVPTimer`, opens Settings to bind the PTT key, and uses the bundled default abilities.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Albion names missing from the Vosk vocabulary | Respell with common words; editor flags them; checked in the spike |
| Single-letter slot words ("e", "r") misheard | Phrase list restricts output; several phrases per ability; checked in the spike; fall back to slot-free phrases ("blood letter") |
| Antivirus flags the PyInstaller build | One-folder build; document it in the README; code signing is out of scope |
| Global hook conflicts with the game or Discord | pynput only listens and never consumes the key, so the game and Discord still receive it |
| Exclusive fullscreen hides the overlay | README tells users to switch to borderless; beep still works |

## 11. Build order

0. **Spike (throwaway, `spike/`):** a script that records while a key is held and runs Vosk small with a grammar of about 10 realistic phrases (including Albion names and single-letter slots). Questions to answer:
   1. Which words are missing from the vocabulary, and the most reliable way to detect them in code (e.g. the model's `graph/words.txt` if it exists, or another method).
   2. How often single letters are recognized correctly on the user's mic.
   3. Time from key release to result.
   If accuracy is under 90%, try `vosk-model-en-us-0.22-lgraph` (larger, still supports grammars) before changing the design.
1. `store.py` + `timers.py` with unit tests.
2. `overlay.py` + `app.py` tray, using **Debug: fire test timer** (no speech yet). Check in-game.
3. `hotkey.py` + `speech.py` + router, with the end-to-end voice → timer path working.
4. `settings.py` dialog.
5. `editor.py` with Test phrase, import and export.
6. PyInstaller packaging, README, and a test of the zip on a clean machine or user account.
