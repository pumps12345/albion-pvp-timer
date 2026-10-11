"""User settings stored in settings.json (pure data; the dialog lives in settings_dialog.py)."""
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .jsonio import atomic_write_json, load_or_quarantine

SETTINGS_VERSION = 1
MOUSE_BUTTONS = ("x1", "x2", "middle")
BAR_WIDTH_RANGE = (160, 600)
BAR_HEIGHT_RANGE = (16, 64)
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


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
    bar_width: int = 260
    bar_height: int = 26
    color_running: str = "#64748b"
    color_warning: str = "#f59e0b"
    color_ready: str = "#22c55e"

    @staticmethod
    def from_json(data: Any) -> "OverlaySettings":
        d = OverlaySettings()

        def size(key: str, bounds: tuple[int, int]) -> int:
            return min(max(int(data.get(key, getattr(d, key))), bounds[0]), bounds[1])

        def color(key: str) -> str:
            value = data.get(key)
            return value.lower() if isinstance(value, str) and _HEX_COLOR.match(value) else getattr(d, key)

        return OverlaySettings(
            screen=int(data.get("screen", d.screen)),
            x=int(data.get("x", d.x)),
            y=int(data.get("y", d.y)),
            opacity=float(data.get("opacity", d.opacity)),
            bar_width=size("bar_width", BAR_WIDTH_RANGE),
            bar_height=size("bar_height", BAR_HEIGHT_RANGE),
            color_running=color("color_running"),
            color_warning=color("color_warning"),
            color_ready=color("color_ready"),
        )


@dataclass
class Settings:
    ptt: PttBinding | None = None
    always_listen: bool = False  # True: listen continuously, no push-to-talk key needed
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
            "always_listen": self.always_listen,
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
        d = Settings()
        mic = data.get("mic_device")
        if mic is not None and not isinstance(mic, str):
            raise TypeError("mic_device must be a string or null")
        return Settings(
            ptt=PttBinding.from_json(data.get("ptt")),
            always_listen=bool(data.get("always_listen", d.always_listen)),
            mic_device=mic,
            speech_offset_s=float(data.get("speech_offset_s", d.speech_offset_s)),
            warning_s=float(data.get("warning_s", d.warning_s)),
            ready_display_s=float(data.get("ready_display_s", d.ready_display_s)),
            beep_enabled=bool(data.get("beep_enabled", d.beep_enabled)),
            beep_volume=float(data.get("beep_volume", d.beep_volume)),
            overlay=OverlaySettings.from_json(data.get("overlay", {})),
        )


def load_settings(path: Path) -> tuple[Settings, str | None]:
    settings, warning = load_or_quarantine(path, Settings.from_json)
    return settings or Settings(), warning


def save_settings(path: Path, settings: Settings) -> None:
    atomic_write_json(path, settings.to_json())
