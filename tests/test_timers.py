from types import SimpleNamespace

import pytest

from pvptimer.timers import TimerManager, TimerState


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def ability(id="bl", name="Bloodletter E", cooldown_s=15.0):
    return SimpleNamespace(id=id, name=name, cooldown_s=cooldown_s)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def timers(clock):
    return TimerManager(clock=clock, speech_offset_s=0.5, warning_s=3.0, ready_display_s=3.0)


def test_start_backdates_by_speech_offset(timers):
    timers.start(ability())
    [view] = timers.snapshot()
    assert view.remaining_s == pytest.approx(14.5)
    assert view.fraction == pytest.approx(14.5 / 15.0)
    assert view.state is TimerState.RUNNING
    assert view.name == "Bloodletter E"


@pytest.mark.parametrize("elapsed, state", [
    (11.49, TimerState.RUNNING),   # remaining 3.01
    (11.5, TimerState.WARNING),    # remaining exactly warning_s
    (14.4, TimerState.WARNING),
    (14.5, TimerState.READY),      # remaining exactly 0
    (17.49, TimerState.READY),
])
def test_state_boundaries(timers, clock, elapsed, state):
    timers.start(ability())
    clock.now += elapsed
    assert timers.snapshot()[0].state is state


def test_timer_removed_after_ready_display(timers, clock):
    timers.start(ability())
    clock.now += 14.5 + 3.0
    assert timers.snapshot() == []


def test_restart_replaces_existing_timer(timers, clock):
    timers.start(ability())
    clock.now += 10
    timers.start(ability())
    views = timers.snapshot()
    assert len(views) == 1
    assert views[0].remaining_s == pytest.approx(14.5)


def test_ready_event_fires_once_and_again_after_restart(timers, clock):
    timers.start(ability())
    clock.now += 14.0
    assert timers.ready_events() == []
    clock.now += 0.5
    assert timers.ready_events() == ["bl"]
    assert timers.ready_events() == []
    timers.start(ability())
    clock.now += 14.5
    assert timers.ready_events() == ["bl"]


def test_clear_and_clear_all(timers):
    timers.start(ability(id="a"))
    timers.start(ability(id="b"))
    timers.clear("a")
    assert [v.ability_id for v in timers.snapshot()] == ["b"]
    timers.clear("missing")
    timers.clear_all()
    assert timers.snapshot() == []


def test_snapshot_sorted_soonest_first(timers):
    timers.start(ability(id="long", cooldown_s=60))
    timers.start(ability(id="short", cooldown_s=10))
    assert [v.ability_id for v in timers.snapshot()] == ["short", "long"]


def test_offset_longer_than_cooldown_is_immediately_ready(timers):
    timers.start(ability(cooldown_s=0.3))
    [view] = timers.snapshot()
    assert view.state is TimerState.READY
    assert view.fraction == 0.0
    assert timers.ready_events() == ["bl"]
    assert timers.ready_events() == []


def test_setting_changes_apply_to_later_starts(timers):
    timers.speech_offset_s = 0.0
    timers.start(ability())
    assert timers.snapshot()[0].remaining_s == pytest.approx(15.0)
