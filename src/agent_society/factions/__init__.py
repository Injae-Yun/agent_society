"""Faction & reputation subsystem (M6).

Public API:
    from agent_society.factions import (
        DEFAULT_FACTIONS, role_to_faction,
        apply_quest_completion_reputation, propagate_rumors,
        REP_TIER,
    )
"""

from agent_society.factions.registry import (
    DEFAULT_FACTIONS,
    ROLE_TO_FACTION,
    role_to_faction,
)
from agent_society.factions.reputation import (
    REP_TIER,
    apply_quest_completion_reputation,
    propagate_rumors,
    reputation_tier,
)

__all__ = [
    "DEFAULT_FACTIONS",
    "REP_TIER",
    "ROLE_TO_FACTION",
    "apply_quest_completion_reputation",
    "propagate_rumors",
    "reputation_tier",
    "role_to_faction",
]
