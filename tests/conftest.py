import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real %APPDATA%\\PVPTimer during tests."""
    home = tmp_path / "home"
    monkeypatch.setenv("PVPTIMER_HOME", str(home))
    return home
