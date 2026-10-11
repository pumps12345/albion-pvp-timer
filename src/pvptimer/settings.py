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
