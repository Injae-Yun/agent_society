"""SimulationDriver — orchestrates the per-tick execution order."""

from __future__ import annotations

import logging

from agent_society.agents.society import AgentSociety
from agent_society.config.parameters import QUEST_REFRESH_INTERVAL
from agent_society.events.bus import WorldEventBus
from agent_society.events.generator import EventGenerator
from agent_society.schema import World
from agent_society.simulation.clock import format_time
from agent_society.world.snapshot import WorldSnapshot

log = logging.getLogger(__name__)


class SimulationDriver:
    """Tick order (ARCHITECTURE.md §4.1):
    1. EventGenerator.tick(snapshot)
    2. bus.drain(world)
    3. AgentSociety.tick(world)  → returns [(agent_id, action)]
    4. bus.drain(world)
    5. QuestGenerator (every QUEST_REFRESH_INTERVAL)
    6. PlayerInterface
    7. bus.drain(world)
    8. Expire old events
    9. recorder.record_tick() if recorder attached
    10. world.tick += 1
    """

    def __init__(
        self,
        world: World,
        event_gen: EventGenerator,
        agent_society: AgentSociety,
        bus: WorldEventBus,
        quest_gen: object | None = None,
        player: object | None = None,
        recorder: object | None = None,
    ) -> None:
        self.world = world
        self._event_gen = event_gen
        self._agent_society = agent_society
        self._bus = bus
        self._quest_gen = quest_gen
        self._player = player
        self._recorder = recorder

    def world_tick(self) -> None:
        w = self.world

        # 1. External events
        self._event_gen.tick(WorldSnapshot(w))

        # 2. Apply events
        fired = self._bus.drain(w)
        w.active_events.extend(fired)

        # 3. Agent society — collect actions for recorder
        tick_actions = self._agent_society.tick(w)

        # 4. Agent-triggered events
        fired = self._bus.drain(w)
        w.active_events.extend(fired)

        # 5. Quest generator (every 7 in-game days)
        if self._quest_gen is not None and w.tick > 0 and w.tick % QUEST_REFRESH_INTERVAL == 0:
            self._quest_gen.tick(WorldSnapshot(w))  # type: ignore[union-attr]

        # 6. Player / free NPC I/O
        if self._player is not None:
            self._player.tick(w)  # type: ignore[union-attr]
            fired = self._bus.drain(w)
            w.active_events.extend(fired)

        # 7. Expire events
        w.active_events = [e for e in w.active_events if not e.is_expired(w.tick)]

        # 8. Record this tick
        if self._recorder is not None:
            self._recorder.record_tick(w, tick_actions, quest_gen=self._quest_gen)

        # 9. Advance tick
        w.tick += 1

        if w.tick % 144 == 0:
            log.info("=== %s ===", format_time(w.tick))

    def run(self, n_ticks: int) -> None:
        for _ in range(n_ticks):
            self.world_tick()

    def summary(self) -> str:
        w = self.world
        lines = [
            f"Tick: {w.tick} ({format_time(w.tick)})",
            f"Agents: {len(w.agents)}",
            f"Active events: {len(w.active_events)}",
        ]
        all_goods: set[str] = set()
        for node in w.nodes.values():
            all_goods.update(node.stockpile.keys())
        for good in sorted(all_goods):
            if good.startswith("_"):
                continue
            total = sum(n.stockpile.get(good, 0) for n in w.nodes.values())
            if total:
                lines.append(f"  {good}: {total}")
        return "\n".join(lines)
