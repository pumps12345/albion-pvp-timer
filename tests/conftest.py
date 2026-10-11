import pytest

from pvptimer.abilities import Ability


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real %APPDATA%\\PVPTimer during tests."""
    home = tmp_path / "home"
    monkeypatch.setenv("PVPTIMER_HOME", str(home))
    return home


@pytest.fixture
def make_ability():
    def factory(id="bloodletter_e", name="Bloodletter E", slot="E", cooldown_s=15.0,
                phrases=("blood letter e",), category="custom"):
        return Ability(id, name, slot, cooldown_s, tuple(phrases), category)
    return factory
