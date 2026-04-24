"""Default faction set for the MVP world.

Three blocs cover the current 9 roles:
  * civic    — city-dwellers, quest brokers, adventurers, the Player
  * rural    — farm producers
  * raiders  — hostile faction, starts at −40 with every other faction

Scenario YAML may extend / override this list. The `role_to_faction()`
helper gives a builder a safe default when the yaml omits explicit mapping.
"""

from __future__ import annotations

from agent_society.schema import Faction, Role


DEFAULT_FACTIONS: dict[str, Faction] = {
    "civic":   Faction(id="civic",   name="Civic Alliance", home_region="city"),
    "rural":   Faction(id="rural",   name="Rural Commons",  home_region="farmland"),
    "raiders": Faction(id="raiders", name="Shadow Band",    home_region="raider_base",
                       hostile_by_default=True),
}


# Role → faction_id fallback when scenario yaml doesn't specify.
ROLE_TO_FACTION: dict[Role, str] = {
    Role.FARMER:     "rural",
    Role.HERDER:     "rural",
    Role.MINER:      "rural",
    Role.ORCHARDIST: "rural",
    Role.BLACKSMITH: "civic",
    Role.COOK:       "civic",
    Role.MERCHANT:   "civic",
    Role.ADVENTURER: "civic",
    Role.PLAYER:     "civic",
    Role.RAIDER:     "raiders",
}


def role_to_faction(role: Role) -> str | None:
    """Return the default faction_id for a role, or None if unmapped."""
    return ROLE_TO_FACTION.get(role)
