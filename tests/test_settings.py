import json

from pvptimer.settings import OverlaySettings, PttBinding, Settings, load_settings, save_settings


def test_missing_file_gives_defaults(tmp_path):
    settings, warning = load_settings(tmp_path / "settings.json")
    assert warning is None
    assert settings == Settings()
    assert settings.ptt is None
    assert settings.speech_offset_s == 0.7
    assert settings.overlay == OverlaySettings(0, 40, 200, 0.9)


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(ptt=PttBinding("mouse", "x1"), mic_device="Headset Mic", speech_offset_s=1.0,
                 warning_s=5.0, ready_display_s=2.0, beep_enabled=False, beep_volume=0.3,
                 overlay=OverlaySettings(1, 10, 20, 0.5))
    save_settings(path, s)
    assert load_settings(path) == (s, None)


def test_file_shape_matches_spec(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(ptt=PttBinding("keyboard", "f8")))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["ptt"] == {"device": "keyboard", "key": "f8"}
    assert data["overlay"] == {"screen": 0, "x": 40, "y": 200, "opacity": 0.9}


def test_partial_file_fills_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"version": 1, "warning_s": 5}', encoding="utf-8")
    settings, warning = load_settings(path)
    assert warning is None
    assert settings.warning_s == 5.0
    assert settings.beep_volume == 0.6


def test_invalid_file_is_quarantined(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"version": 1, "ptt": {"device": "mouse", "button": "left"}}', encoding="utf-8")
    settings, warning = load_settings(path)
    assert settings == Settings()
    assert warning
    assert not path.exists()


def test_binding_labels():
    assert PttBinding("mouse", "x1").label() == "Mouse X1"
    assert PttBinding("keyboard", "f8").label() == "Key F8"
