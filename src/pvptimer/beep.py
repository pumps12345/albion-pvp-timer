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
