import json

from pvptimer.jsonio import atomic_write_json, load_or_quarantine


def test_atomic_write_round_trips_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "sub" / "data.json"
    atomic_write_json(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert [p.name for p in path.parent.iterdir()] == ["data.json"]


def test_load_missing_file_returns_nothing(tmp_path):
    assert load_or_quarantine(tmp_path / "nope.json", dict) == (None, None)


def test_load_parses_with_given_function(tmp_path):
    path = tmp_path / "d.json"
    path.write_text('{"x": 2}', encoding="utf-8")
    assert load_or_quarantine(path, lambda d: d["x"]) == (2, None)


def test_unreadable_json_is_quarantined(tmp_path):
    path = tmp_path / "d.json"
    path.write_text("{not json", encoding="utf-8")
    value, warning = load_or_quarantine(path, dict)
    assert value is None
    assert "d.json" in warning
    assert not path.exists()
    assert len(list(tmp_path.glob("d.json.bad-*"))) == 1


def test_wrong_shape_is_quarantined(tmp_path):
    path = tmp_path / "d.json"
    path.write_text('{"y": 1}', encoding="utf-8")
    value, warning = load_or_quarantine(path, lambda d: d["x"])
    assert value is None and warning
