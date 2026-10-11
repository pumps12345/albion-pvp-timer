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
