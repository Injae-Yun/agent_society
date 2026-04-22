"""World-state changes triggered by quest completion.

Applied by the tick that finalises a quest (Adventurer or Player). The effects
are what make quests actually matter for economic / faction equilibrium:

    raider_suppress → drops raider strength
    bulk_delivery   → injects goods into the shortage node
    road_restore    → clears a severed edge
    escort          → lowers safety pressure for affected agents

Returns a summary dict that's logged and attached to the recorder.
"""

from __future__ import annotations

import logging

from agent_society.schema import NeedType, QuestIntent, RaiderFaction, World

log = logging.getLogger(__name__)


# Magnitudes — tune in one spot. These are the *baseline* (outcome=SUCCESS).
# d20 check outcomes scale them via `multiplier` argument.
_RAIDER_STRENGTH_CUT = 25.0
_BULK_DELIVERY_UNITS = 15
_ESCORT_SAFETY_RELIEF = 0.3


def apply_completion(quest: QuestIntent, world: World, multiplier: float = 1.0) -> dict:
    """Mutate `world` according to `quest.quest_type`.

    `multiplier` lets the caller scale all numeric effects (e.g. DnD check
    outcome: crit_success=1.5, partial=0.7, crit_failure=0). Defaults to 1.0
    so existing Adventurer code path (no check) stays identical.
    """
    handler = _HANDLERS.get(quest.quest_type)
    if handler is None:
        log.warning("No effect handler for quest_type=%s", quest.quest_type)
        return {"effect": "none"}
    return handler(quest, world, multiplier)


# ── Per-type handlers ─────────────────────────────────────────────────────────

def _raider_suppress(quest: QuestIntent, world: World, mult: float) -> dict:
    cut = _RAIDER_STRENGTH_CUT * mult
    weakened = 0
    for agent in world.agents.values():
        if isinstance(agent, RaiderFaction):
            before = agent.strength
            agent.strength = max(0.0, agent.strength - cut)
            weakened += int(before - agent.strength)
    # Safety needs relief for everyone — the world feels safer for a while
    relief = 0.4 * mult
    for agent in world.agents.values():
        if isinstance(agent, RaiderFaction):
            continue
        agent.needs[NeedType.SAFETY] = max(
            0.0, agent.needs.get(NeedType.SAFETY, 0.0) - relief,
        )
    return {"effect": "raider_suppress", "strength_cut": weakened, "mult": mult}


def _bulk_delivery(quest: QuestIntent, world: World, mult: float) -> dict:
    """`quest.target` is a good name — inject units into the node that's short."""
    good = quest.target
    qty = max(1, int(round(_BULK_DELIVERY_UNITS * mult)))
    # Prefer city (consumption hub) as the delivery point; fallback to farm.
    for node_id in ("city", "farm"):
        node = world.nodes.get(node_id)
        if node is None:
            continue
        node.stockpile[good] = node.stockpile.get(good, 0) + qty
        return {"effect": "bulk_delivery", "good": good, "qty": qty, "node": node_id, "mult": mult}
    return {"effect": "bulk_delivery_failed", "reason": "no hub node"}


def _road_restore(quest: QuestIntent, world: World, mult: float) -> dict:
    """`quest.target` is formatted as `u→v`.

    Critical failures (mult == 0) leave the road broken. Otherwise the edge
    is restored regardless of partial/success — the distinction is in the
    narration, not the binary outcome.
    """
    if mult <= 0:
        return {"effect": "road_restore_failed", "mult": mult}
    if "→" in quest.target:
        u, v = quest.target.split("→", 1)
    else:
        u, v = quest.target, ""
    for edge in world.edges:
        if edge.severed and ((edge.u == u and edge.v == v) or (edge.u == v and edge.v == u)):
            edge.severed = False
            return {"effect": "road_restore", "edge": f"{edge.u}↔{edge.v}", "mult": mult}
    return {"effect": "road_restore_noop", "mult": mult}


def _escort(quest: QuestIntent, world: World, mult: float) -> dict:
    """Relieve safety for supporters (the ones who originally raised the quest)."""
    relief = _ESCORT_SAFETY_RELIEF * mult
    count = 0
    for aid in quest.supporters:
        agent = world.agents.get(aid)
        if agent is None:
            continue
        agent.needs[NeedType.SAFETY] = max(
            0.0, agent.needs.get(NeedType.SAFETY, 0.0) - relief,
        )
        count += 1
    return {"effect": "escort", "agents_relieved": count, "mult": mult}


_HANDLERS = {
    "raider_suppress": _raider_suppress,
    "bulk_delivery":   _bulk_delivery,
    "road_restore":    _road_restore,
    "escort":          _escort,
}
