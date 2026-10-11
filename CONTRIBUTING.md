# Contributing to PVPTimer

Bug reports, ideas and pull requests are welcome. For bugs, please use the
[issue templates](https://github.com/twasser/albion-pvp-timer/issues/new/choose) and attach
`%APPDATA%\PVPTimer\pvptimer.log`.

## Development setup

Requires Windows 10/11 and Python 3.13.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python scripts/get_model.py      # downloads the Vosk speech model into models/
.venv/Scripts/python -m pytest                 # run the tests
.venv/Scripts/python -m pvptimer               # run the app from source
```

Set `PVPTIMER_HOME` to a scratch folder to run with throwaway settings instead of
`%APPDATA%\PVPTimer`.

## Project layout

| Path | What it is |
|---|---|
| `src/pvptimer/app.py` | Wiring: main window, overlay, timers, push-to-talk, speech |
| `src/pvptimer/abilities.py`, `store.py` | Ability model, validation, built-in + user lists |
| `src/pvptimer/timers.py`, `router.py` | Countdown logic and what a recognized phrase means (pure, no Qt) |
| `src/pvptimer/speech.py`, `hotkey.py` | Vosk recognition gated by push-to-talk (pynput) |
| `src/pvptimer/overlay.py` | The click-through overlay and bar drawing |
| `src/pvptimer/main_window.py`, `editor.py`, `settings_dialog.py` | The UI |
| `src/pvptimer/gamedata.py`, `scripts/import_game_data.py` | Generates the built-in ability list from game data |
| `docs/superpowers/` | The original design spec and implementation plan |

## The built-in ability list

`src/pvptimer/data/default_abilities.json` is generated from the community game-data dumps at
[ao-data/ao-bin-dumps](https://github.com/ao-data/ao-bin-dumps). After a game patch, regenerate it:

```bash
.venv/Scripts/python scripts/import_game_data.py
```

It writes `build/import_report.txt`, listing:
- phrases with words the speech model doesn't know (add a sound-alike to `SPOKEN` in
  `src/pvptimer/gamedata.py`);
- cooldowns read from the second stage of two-stage abilities (worth checking in game);
- anything skipped.

## Making a release

1. Bump `__version__` in `src/pvptimer/__init__.py` and `version` in `pyproject.toml`, and add an entry
   to `CHANGELOG.md`.
2. Refresh the README screenshots if the UI changed: `.venv/Scripts/python scripts/make_screenshots.py`.
3. Build: `.venv/Scripts/python scripts/make_release.py`. This produces `dist/PVPTimer-<version>.zip`
   (with license files and "Read me first.txt" inside) and a `.sha256` checksum file.
4. Tag the commit (`git tag v<version>` and `git push --tags`), then create a GitHub release for the tag.
   Attach the zip and paste the SHA-256 into the notes, e.g.
   `gh release create v<version> dist/PVPTimer-<version>.zip --notes-file <notes>`.
