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
