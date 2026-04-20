"""EventGenerator — evaluates catalog conditions each tick and publishes events."""

from __future__ import annotations

import logging
from random import Random

from agent_society.events.bus import WorldEventBus
from agent_society.events.catalog import DEFAULT_CATALOG, EventTemplate
from agent_society.world.snapshot import WorldSnapshot

log = logging.getLogger(__name__)


class EventGenerator:
    def __init__(
        self,
        bus: WorldEventBus,
        catalog: list[EventTemplate] | None = None,
        rng: Random | None = None,
    ) -> None:
        self._bus = bus
        self._catalog = catalog if catalog is not None else list(DEFAULT_CATALOG)
        self._rng = rng or Random()

    def tick(self, snapshot: WorldSnapshot) -> None:
        current_tick = snapshot.tick
        for template in self._catalog:
            if template.on_cooldown(current_tick):
                continue
            try:
                if not template.condition(snapshot):
                    continue
                weight = template.weight(snapshot)
            except Exception:
                log.exception("Error evaluating event template %r", template.name)
                continue

            if self._rng.random() < weight:
                event = template.instantiate(current_tick, source="event_gen")
                self._bus.publish(event)
                template.mark_fired(current_tick)
                log.info("tick=%d  event=%s published", current_tick, template.name)
