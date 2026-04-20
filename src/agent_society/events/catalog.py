"""Event catalog — templates with conditions, weights, and cooldowns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Type

from agent_society.config.balance import GOLD_TAX_RATE, GOLD_TAX_THRESHOLD
from agent_society.events.types import (
    EventSeverity,
    GoldTax,
    HarvestBoom,
    HarvestFailure,
    RaiderDecline,
    RaiderSurge,
    WorldEvent,
)
from agent_society.schema import RegionType, Role
from agent_society.world.snapshot import WorldSnapshot


@dataclass
class EventTemplate:
    name: str
    event_cls: Type[WorldEvent]
    severity: EventSeverity
    condition: Callable[[WorldSnapshot], bool]
    weight: Callable[[WorldSnapshot], float]
    cooldown: int                   # minimum ticks between activations
    kwargs: dict = field(default_factory=dict)  # extra fields passed to event_cls
    _last_fired: int = field(default=-999999, init=False, repr=False)

    def on_cooldown(self, current_tick: int) -> bool:
        return (current_tick - self._last_fired) < self.cooldown

    def mark_fired(self, tick: int) -> None:
        self._last_fired = tick

    def instantiate(self, tick: int, source: str) -> WorldEvent:
        return self.event_cls(
            tick=tick,
            source=source,
            severity=self.severity,
            **self.kwargs,
        )


def _total_agent_gold(snap: WorldSnapshot) -> int:
    return sum(getattr(a, "gold", 0) for a in snap._world.agents.values())  # type: ignore[attr-defined]


def _raider_faction(snap: WorldSnapshot):
    agents = snap.agents_by_role(Role.RAIDER)
    return agents[0] if agents else None


DEFAULT_CATALOG: list[EventTemplate] = [
    EventTemplate(
        name="harvest_failure",
        event_cls=HarvestFailure,
        severity=EventSeverity.MAJOR,
        condition=lambda snap: snap.total_stock("wheat") < 10,
        weight=lambda snap: 1.0,
        cooldown=4320 * 3,  # ~3 years
        kwargs={"region": RegionType.FARMLAND, "duration": 4320},
    ),
    EventTemplate(
        name="harvest_boom",
        event_cls=HarvestBoom,
        severity=EventSeverity.MAJOR,
        condition=lambda snap: snap.total_stock("wheat") > 50,
        weight=lambda snap: 0.5,
        cooldown=4320 * 3,
        kwargs={"region": RegionType.FARMLAND, "duration": 4320},
    ),
    EventTemplate(
        name="raider_surge",
        event_cls=RaiderSurge,
        severity=EventSeverity.MAJOR,
        condition=lambda snap: (
            (r := _raider_faction(snap)) is not None
            and hasattr(r, "strength") and r.strength < 50
            and snap.total_stock("meat") + snap.total_stock("wheat") < 5
        ),
        weight=lambda snap: 1.0,
        cooldown=1440,  # once per 10 days
        kwargs={"delta_strength": 30.0},
    ),
    EventTemplate(
        name="gold_tax",
        event_cls=GoldTax,
        severity=EventSeverity.INFO,
        condition=lambda snap: _total_agent_gold(snap) > GOLD_TAX_THRESHOLD,
        weight=lambda snap: 1.0,
        cooldown=168,   # 최소 1주일(7일) 간격
        kwargs={"tax_rate": GOLD_TAX_RATE, "duration": 0},
    ),
    EventTemplate(
        name="raider_decline",
        event_cls=RaiderDecline,
        severity=EventSeverity.MINOR,
        condition=lambda snap: (
            (r := _raider_faction(snap)) is not None
            and hasattr(r, "strength") and r.strength > 80
        ),
        weight=lambda snap: 0.3,
        cooldown=2880,
        kwargs={"delta_strength": 30.0},
    ),
]
