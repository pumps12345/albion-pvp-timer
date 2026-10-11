from pvptimer import paths


def test_data_dir_contains_bundled_files():
    assert (paths.data_dir() / "default_abilities.json").is_file()
    assert (paths.data_dir() / "ready.wav").is_file()


def test_model_dir_is_under_repo_models_folder():
    model = paths.model_dir()
    assert model.name == paths.MODEL_NAME
    assert model.parent.name == "models"
    assert (model.parent.parent / "pyproject.toml").is_file()


def test_app_data_dir_uses_override_and_creates_it(tmp_path, monkeypatch):
    target = tmp_path / "custom"
    monkeypatch.setenv("PVPTIMER_HOME", str(target))
    assert paths.app_data_dir() == target
    assert target.is_dir()


def test_app_data_dir_defaults_to_appdata(tmp_path, monkeypatch):
    monkeypatch.delenv("PVPTIMER_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.app_data_dir() == tmp_path / "PVPTimer"
