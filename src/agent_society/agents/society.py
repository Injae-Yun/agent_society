"""AgentSociety — tick orchestrator for all agents."""

from __future__ import annotations

import logging
from random import Random

from agent_society.agents.needs import decay_needs
from agent_society.agents.selection import select_action
from agent_society.events.bus import WorldEventBus
from agent_society.events.handlers import register_all_handlers
from agent_society.schema import AdventurerAgent, PlayerAgent, RaiderFaction, World
from agent_society.world.snapshot import WorldSnapshot

log = logging.getLogger(__name__)


class AgentSociety:
    def __init__(
        self,
        bus: WorldEventBus,
        rng: Random | None = None,
        quest_gen: object | None = None,
        player_interface: object | None = None,
    ) -> None:
        self._bus = bus
        self._rng = rng or Random()
        self._quest_gen = quest_gen
        self._player_interface = player_interface
        register_all_handlers(bus)

    def set_quest_gen(self, quest_gen: object) -> None:
        """Allow the driver to wire up the quest generator after construction."""
        self._quest_gen = quest_gen

    def set_player_interface(self, player_interface: object) -> None:
        """Wire the player input source after construction."""
        self._player_interface = player_interface

    def tick(self, world: World) -> list[tuple[str, object]]:
        """Run one tick for all agents (ID-ascending). Returns [(agent_id, action)] for recorder."""
        snapshot = WorldSnapshot(world)
        executed: list[tuple[str, object]] = []

        for agent_id in sorted(world.agents.keys()):
            agent = world.agents[agent_id]
            try:
                action = self._tick_agent(agent, world, snapshot)
                executed.append((agent_id, action))
            except Exception:
                log.exception("Error ticking agent %s — skipping", agent_id)

        return executed

    def _tick_agent(self, agent, world: World, snapshot: WorldSnapshot) -> object:
        from agent_society.agents.actions import NoAction

        # 1. Needs decay
        decay_needs(agent)

        # 1b. Raider-specific: scaled food consumption + strength decay on starvation
        if isinstance(agent, RaiderFaction):
            _tick_raider_maintenance(agent, world)

        # 2. If in transit — wait
        if agent.travel_ticks_remaining > 0:
            agent.travel_ticks_remaining -= 1
            action = NoAction(agent=agent)
            action.action_type = "transit"   # distinct from idle: agent is moving
            action._last_delta = {}
            return action

        # 2b. Passive weapon wear — slow maintenance wear (combat damage is separate)
        if agent.equipped_weapon:
            agent.equipped_weapon.durability = max(0.0, agent.equipped_weapon.durability - 0.05)

        # 3. Choose action — Player / Adventurer / NPC paths diverge here.
        #    PlayerAgent check runs first because it inherits from AdventurerAgent.
        if isinstance(agent, PlayerAgent):
            from agent_society.agents.player import tick_player
            action = tick_player(
                agent, world, self._bus, self._quest_gen,
                self._player_interface, snapshot, self._rng,
            )
        elif isinstance(agent, AdventurerAgent) and self._quest_gen is not None:
            from agent_society.agents.adventurer import tick_adventurer
            action = tick_adventurer(
                agent, world, self._bus, self._quest_gen, snapshot, self._rng,
            )
        else:
            action = select_action(agent, snapshot, self._rng)

        # 4. Execute — store delta on action for recorder
        delta = action.execute(world, self._bus)
        action._last_delta = delta if isinstance(delta, dict) else {}

        # Re-enforce raider armory cap after loot from this action
        if isinstance(agent, RaiderFaction) and agent.inventory.get("sword", 0) > _MAX_RAIDER_WEAPONS:
            agent.inventory["sword"] = _MAX_RAIDER_WEAPONS

        return action


_RAIDER_FOOD_GOODS = ("cooked_meal", "fruit", "meat", "wheat")
_RAIDER_HIDEOUT = "raider.hideout"
_RAIDER_STRENGTH_DECAY = 0.2   # strength lost per tick when unfed
_MAX_RAIDER_WEAPONS = 15       # faction armory cap — excess swords wear out / distributed
_RAIDER_PASSIVE_FOOD = 2       # meat/tick from hideout hunting/foraging (matches ~demand at str 40-50)


def _tick_raider_maintenance(raider: RaiderFaction, world: World) -> None:
    """Raider food consumption and strength management.

    Passive food production (hunting/foraging) supplements raid loot.
    Demand = max(1, floor(strength/20)) — simpler, armory doesn't eat.
    Consumes first from hideout stockpile, then from raider's own inventory.
    Decays strength if unfed; regenerates (up to 70) when fed.
    """
    hideout = world.nodes.get(_RAIDER_HIDEOUT)
    if hideout is None:
        return

    # Passive food production — hideout hunters/foragers provide baseline
    hideout.stockpile["meat"] = hideout.stockpile.get("meat", 0) + _RAIDER_PASSIVE_FOOD

    # Cap faction armory (excess weapons are broken/distributed off-screen)
    if raider.inventory.get("sword", 0) > _MAX_RAIDER_WEAPONS:
        raider.inventory["sword"] = _MAX_RAIDER_WEAPONS

    food_demand = max(1, int(raider.strength / 20))

    remaining = food_demand

    # 1. Consume from hideout stockpile first
    for good in _RAIDER_FOOD_GOODS:
        available = hideout.stockpile.get(good, 0)
        consume = min(remaining, available)
        if consume > 0:
            hideout.stockpile[good] -= consume
            remaining -= consume
        if remaining <= 0:
            break

    # 2. Then from raider's personal inventory (looted food carried on raids)
    if remaining > 0:
        for good in _RAIDER_FOOD_GOODS:
            available = raider.inventory.get(good, 0)
            consume = min(remaining, available)
            if consume > 0:
                raider.inventory[good] -= consume
                remaining -= consume
            if remaining <= 0:
                break

    # 3. Still unfed — decay strength
    if remaining > 0:
        raider.strength = max(10.0, raider.strength - _RAIDER_STRENGTH_DECAY)
        log.debug("Raider unfed by %d units — strength → %.1f", remaining, raider.strength)

    # 4. Strength regeneration when well-fed — slow passive recovery.
    #    Caps at 40 — base equilibrium; raids are the only path above this.
    if remaining == 0 and raider.strength < 50.0:
        raider.strength = min(50.0, raider.strength + 0.2)

    # 5. Forge swords from looted ore (3 ore → 1 sword)
    _ORE_PER_SWORD = 3
    ore_inv = raider.inventory.get("ore", 0)
    ore_stockpile = hideout.stockpile.get("ore", 0)
    current_armory = raider.inventory.get("sword", 0)
    if ore_inv + ore_stockpile >= _ORE_PER_SWORD and current_armory < _MAX_RAIDER_WEAPONS:
        # Use personal ore first, then hideout stockpile
        if ore_inv >= _ORE_PER_SWORD:
            raider.inventory["ore"] = ore_inv - _ORE_PER_SWORD
        else:
            used_inv = ore_inv
            raider.inventory["ore"] = 0
            hideout.stockpile["ore"] = ore_stockpile - (_ORE_PER_SWORD - used_inv)
        raider.inventory["sword"] = current_armory + 1
        log.debug("Raider forged sword from ore (armory: %d)", raider.inventory["sword"])

    # Re-apply cap after forging + loot accumulation in the same tick
    if raider.inventory.get("sword", 0) > _MAX_RAIDER_WEAPONS:
        raider.inventory["sword"] = _MAX_RAIDER_WEAPONS


