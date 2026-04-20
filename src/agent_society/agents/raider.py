"""Raider-specific logic — strength management and raid resolution."""

from __future__ import annotations

import random as _random

from agent_society.config.balance import (
    DESTRUCTION_FACTOR,
    RAID_RATE,
    STRENGTH_GAIN_FROM_SUCCESS,
    STRENGTH_LOSS_FROM_FAILURE,
    WEAPON_POWER,
)
from agent_society.schema import Agent, RaiderFaction


def weapon_power(agent: Agent) -> int:
    if agent.equipped_weapon is None or not agent.equipped_weapon.is_usable():
        return 0
    return WEAPON_POWER.get(agent.equipped_weapon.type, 0)


def total_defense(defenders: list[Agent]) -> int:
    """Defense = the strongest single armed defender encountered.

    Merchants on a route are spread out over time; the raider intercepts them
    one at a time, not as a coordinated group.  Clustering at the same map node
    is a graph abstraction — it does NOT multiply defensive power.
    """
    if not defenders:
        return 0
    return max(weapon_power(a) for a in defenders)


def raid_resolution(
    raider: RaiderFaction,
    defenders: list[Agent],
    node_stockpile: dict[str, int],
) -> tuple[str, dict[str, int], dict]:
    """Resolve a raid attempt.

    Returns:
        (result, loot, combat_info) where result is one of "repelled", "partial_loss",
        "plundered"; loot is the dict of goods taken; combat_info has attack/defense values.
    """
    defense = total_defense(defenders)
    armory = raider.inventory.get("sword", 0)
    effective_attack = raider.strength + armory * 2.0   # each sword = +2 attack; armory is primary power driver
    combat_info = {"attack": round(effective_attack, 1), "defense": defense, "armory": armory}

    if defense >= effective_attack:
        # Defenders win — consume weapon durability for each armed defender
        for defender in defenders:
            if defender.has_usable_weapon() and defender.equipped_weapon:
                defender.equipped_weapon.durability = max(0, defender.equipped_weapon.durability - 1)
        raider.strength = max(10.0, raider.strength - STRENGTH_LOSS_FROM_FAILURE)  # floor at 10
        return "repelled", {}, combat_info

    # Loot rate scales with combat dominance — a narrow victory yields little
    combat_margin = (effective_attack - defense) / max(effective_attack, 1.0)
    rate = min(0.70, 0.15 + combat_margin * 0.55)

    loot: dict[str, int] = {}
    for good, qty in node_stockpile.items():
        if good.startswith("_"):  # internal markers
            continue
        taken = max(0, int(qty * rate))
        if taken:
            loot[good] = taken
            node_stockpile[good] = qty - taken

    # Also loot defender inventories (merchants carrying goods on route)
    for defender in defenders:
        for good, qty in list(defender.inventory.items()):
            if good.startswith("_") or qty <= 0:
                continue
            taken = max(0, int(qty * rate))
            if taken:
                loot[good] = loot.get(good, 0) + taken
                defender.inventory[good] = qty - taken

    # Weapon looting: only the primary defender (highest weapon power) loses their
    # weapon — others escape with theirs.  A raider gang overwhelms one fighter;
    # the rest scatter.
    if defenders:
        primary = max(defenders, key=weapon_power)
        if primary.has_usable_weapon() and primary.equipped_weapon:
            loot["sword"] = loot.get("sword", 0) + 1
            primary.equipped_weapon = None

    # Some loot is destroyed
    destroyed: dict[str, int] = {}
    for good, qty in loot.items():
        destroyed[good] = int(qty * DESTRUCTION_FACTOR)

    net_loot = {g: q - destroyed.get(g, 0) for g, q in loot.items() if q - destroyed.get(g, 0) > 0}

    # Raider weapon wear: each sword has 5% independent chance of breaking per raid
    armory_before = raider.inventory.get("sword", 0)
    broken = sum(1 for _ in range(armory_before) if _random.random() < 0.05)
    raider.inventory["sword"] = max(0, armory_before - broken)

    # Consume defender weapon durability for armed defenders still holding their weapons
    for defender in defenders:
        if defender.has_usable_weapon() and defender.equipped_weapon:
            defender.equipped_weapon.durability = max(0, defender.equipped_weapon.durability - 1)

    if defense > 0:
        # Some defense — partial loss
        raider.strength = min(55.0, raider.strength + STRENGTH_GAIN_FROM_SUCCESS * 0.5)
        return "partial_loss", net_loot, combat_info

    # No defense — full plunder
    raider.strength = min(55.0, raider.strength + STRENGTH_GAIN_FROM_SUCCESS)
    return "plundered", net_loot, combat_info
