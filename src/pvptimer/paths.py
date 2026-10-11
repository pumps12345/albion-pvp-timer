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
