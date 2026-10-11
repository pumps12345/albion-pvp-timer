"""Render the README screenshots into docs/images/ (main window, settings, overlay bars).

Usage: .venv/Scripts/python scripts/make_screenshots.py
Uses a throwaway settings folder, so your own abilities and settings are never touched.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
os.environ["PVPTIMER_HOME"] = tempfile.mkdtemp(prefix="pvptimer-shots-")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pvptimer import paths  # noqa: E402
from pvptimer.editor import EditorWindow  # noqa: E402
from pvptimer.main_window import MainWindow  # noqa: E402
from pvptimer.overlay import ROW_GAP, bar_font, draw_bar  # noqa: E402
from pvptimer.settings import OverlaySettings, PttBinding, Settings  # noqa: E402
from pvptimer.settings_dialog import SettingsDialog  # noqa: E402
from pvptimer.store import AbilityStore  # noqa: E402
from pvptimer.timers import TimerState, TimerView  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)

    store = AbilityStore(paths.data_dir() / "default_abilities.json", paths.app_data_dir() / "abilities.json")
    store.load()
    editor = EditorWindow(store, lambda phrases: set())
    window = MainWindow(editor, QIcon())
    window.resize(900, 640)
    window.show()
    editor.tabs.setCurrentIndex(1)  # Weapons
    editor.search_edit.setText("blood")
    editor.table.selectRow(next(r for r in range(editor.table.rowCount()) if not editor.table.isRowHidden(r)))
    app.processEvents()
    window.grab().save(str(OUT / "main-window.png"))

    dialog = SettingsDialog(Settings(ptt=PttBinding("mouse", "x1")), ["Microphone (Headset)"], ptt=None)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(OUT / "settings.png"))

    style = OverlaySettings(bar_width=300, bar_height=30)
    rows = [TimerView("a", "Bloodletter E", 1.8, 0.05, TimerState.WARNING),
            TimerView("b", "Hunter Hood – Retaliate D", 21.0, 0.47, TimerState.RUNNING),
            TimerView("c", "Dodge F", 9.4, 0.63, TimerState.RUNNING),
            TimerView("d", "Divine Staff E", -0.2, 0.0, TimerState.READY)]
    image = QPixmap(340, 40 + len(rows) * (style.bar_height + ROW_GAP))
    image.fill(QColor("#2b3340"))  # stand-in for a game scene
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(bar_font(app.font(), style))
    for index, view in enumerate(rows):
        y = 20 + index * (style.bar_height + ROW_GAP)
        draw_bar(painter, QRectF(20, y, style.bar_width, style.bar_height), view, style, 3.0)
    painter.end()
    image.save(str(OUT / "overlay.png"))
    print(f"wrote screenshots to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
