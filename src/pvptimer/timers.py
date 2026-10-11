"""Countdown state for enemy abilities. Pure logic: no Qt, clock injected for tests."""
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol


class TimerState(Enum):
    RUNNING = "running"
    WARNING = "warning"
    READY = "ready"


class Timed(Protocol):
    id: str
    name: str
    cooldown_s: float


@dataclass(frozen=True)
class TimerView:
    ability_id: str
    name: str
    remaining_s: float
    fraction: float  # remaining / cooldown, clamped to [0, 1]
    state: TimerState


@dataclass
class _Timer:
    ability_id: str
    name: str
    cooldown_s: float
    end: float
    ready_reported: bool = False


class TimerManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic, speech_offset_s: float = 0.7,
                 warning_s: float = 3.0, ready_display_s: float = 3.0) -> None:
        self._clock = clock
        self.speech_offset_s = speech_offset_s
        self.warning_s = warning_s
        self.ready_display_s = ready_display_s
        self._timers: dict[str, _Timer] = {}

    def start(self, ability: Timed) -> None:
        """Start, or restart, the timer for `ability`, backdated by the speech offset."""
        end = self._clock() - self.speech_offset_s + ability.cooldown_s
        self._timers[ability.id] = _Timer(ability.id, ability.name, ability.cooldown_s, end)

    def clear(self, ability_id: str) -> None:
        self._timers.pop(ability_id, None)

    def clear_all(self) -> None:
        self._timers.clear()

    def ready_events(self) -> list[str]:
        """Ids that reached zero since the last call. Call once per tick, before snapshot()."""
        now = self._clock()
        fired = []
        for t in self._timers.values():
            if not t.ready_reported and now >= t.end:
                t.ready_reported = True
                fired.append(t.ability_id)
        return fired

    def snapshot(self) -> list[TimerView]:
        """Current timers, soonest first. Drops timers whose READY display has ended."""
        now = self._clock()
        self._timers = {k: t for k, t in self._timers.items() if now < t.end + self.ready_display_s}
        return sorted((self._view(t, now) for t in self._timers.values()), key=lambda v: v.remaining_s)

    def _view(self, t: _Timer, now: float) -> TimerView:
        remaining = t.end - now
        if remaining <= 0:
            state = TimerState.READY
        elif remaining <= self.warning_s:
            state = TimerState.WARNING
        else:
            state = TimerState.RUNNING
        fraction = min(1.0, max(0.0, remaining / t.cooldown_s))
        return TimerView(t.ability_id, t.name, remaining, fraction, state)
