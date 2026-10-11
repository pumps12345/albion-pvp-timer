"""Build the Windows release zip: PyInstaller build + license files + quick-start notes + checksum.

Usage: .venv/Scripts/python scripts/make_release.py
Output: dist/PVPTimer-<version>.zip and dist/PVPTimer-<version>.zip.sha256
Quit any running PVPTimer first; Windows locks the files of a running exe.
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from pvptimer import __version__

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP = DIST / "PVPTimer"
REPO_URL = "https://github.com/twasser/albion-pvp-timer"

READ_ME_FIRST = f"""PVPTimer {__version__}: voice-triggered enemy cooldown timers for Albion Online
{REPO_URL}

QUICK START
  1. Double-click PVPTimer.exe. Keep it in this folder: it needs the _internal folder next to it.
     If Windows shows "Windows protected your PC", click "More info" and then "Run anyway".
     The app isn't code-signed yet, so Windows doesn't recognise it.
  2. Pick your push-to-talk key or mouse side button.
  3. Run Albion Online in borderless fullscreen or windowed mode.
  4. Hold push-to-talk, say an enemy ability ("blood letter e", "dodge"), and let go.
     A countdown bar appears on screen.
  5. Minimize PVPTimer while you play. Closing it stops the timers.

Your abilities, settings and log are stored in %APPDATA%\\PVPTimer.
Full instructions and troubleshooting: {REPO_URL}#readme

FAIR PLAY
  PVPTimer only listens to your microphone and draws a window over your screen. It never reads or
  changes the game, its memory or its network traffic, and never presses keys for you. Albion
  Online's Terms and Conditions restrict third-party tools that give players an advantage, and
  whether this one counts is up to Sandbox Interactive. Read their rules and use PVPTimer at your
  own risk: https://albiononline.com/terms_and_conditions

PVPTimer is a fan-made tool, not affiliated with Sandbox Interactive GmbH.
See LICENSE and THIRD_PARTY_NOTICES.md for licenses.
"""


def main() -> int:
    subprocess.run([str(Path(sys.executable).parent / "pyinstaller"), "pvptimer.spec", "--noconfirm"],
                   cwd=ROOT, check=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, APP / name)
    shutil.copytree(ROOT / "licenses", APP / "licenses", dirs_exist_ok=True)
    (APP / "Read me first.txt").write_text(READ_ME_FIRST, encoding="utf-8")

    archive = Path(shutil.make_archive(str(DIST / f"PVPTimer-{__version__}"), "zip", DIST, "PVPTimer"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"\n{archive}\n{archive.stat().st_size / 1_000_000:.0f} MB\nSHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
