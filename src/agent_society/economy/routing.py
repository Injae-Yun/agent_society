"""Agent-to-agent gold routing for purchases.

The design principle: when goods change hands, the money should follow the
real-world counterparty (producer, consumer) rather than being absorbed by
the node as an anonymous pool. Node.gold is only a fallback when the
appropriate counterparty doesn't exist at the transaction location.

Two primitives:

  distribute_to_producers(world, node_id, good, amount)
      → pay producers of `good` who are physically at `node_id` (or, if none,
        any producer in the world). Used by buyers: food consumers, tool
        buyers, merchants acquiring raw goods.

  charge_consumers(world, node_id, good, amount)
      → collect gold from consumer-role agents at `node_id` (or any agent in
        the node as fallback). Used by sellers: merchants unloading goods at
        a destination market.

Both return the amount actually routed; any shortfall should be settled
against node.gold by the caller.
"""

from __future__ import annotations

from agent_society.schema import Role, World

# ── Who makes what / who eats what ────────────────────────────────────────────

PRODUCER_OF: dict[str, Role] = {
    "wheat":          Role.FARMER,
    "meat":           Role.HERDER,
    "fruit":          Role.ORCHARDIST,
    "ore":            Role.MINER,
    "cooked_meal":    Role.COOK,
    "sword":          Role.BLACKSMITH,
    "bow":            Role.BLACKSMITH,
    "plow":           Role.BLACKSMITH,
    "sickle":         Role.BLACKSMITH,
    "pickaxe":        Role.BLACKSMITH,
    "cooking_tools":  Role.BLACKSMITH,
    "pruning_shears": Role.BLACKSMITH,
    "cart":           Role.BLACKSMITH,
}

# Primary consumers, in preference order. Merchants selling at a market
# charge the first role found that has agents present + gold; falling back
# through the list. If none match, any agent in the node pays.
CONSUMER_OF: dict[str, tuple[Role, ...]] = {
    "wheat":          (Role.COOK,),                      # kitchen ingredient
    "meat":           (Role.COOK,),
    "fruit":          (Role.COOK, Role.ORCHARDIST),      # cooking or re-sale
    "ore":            (Role.BLACKSMITH,),                # smithy input
    "cooked_meal":    (),                                # anyone eats it
    "sword":          (Role.MERCHANT,),                  # merchants self-arm
    "plow":           (Role.FARMER,),
    "sickle":         (Role.HERDER, Role.FARMER),
    "pickaxe":        (Role.MINER,),
    "cooking_tools":  (Role.COOK,),
    "pruning_shears": (Role.ORCHARDIST,),
    "bow":            (Role.MERCHANT,),
    "cart":           (Role.MERCHANT,),
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _locals_of_role(world: World, node_id: str, role: Role) -> list:
    return [
        world.agents[aid]
        for aid in world.agents_by_node.get(node_id, [])
        if aid in world.agents and world.agents[aid].role == role
    ]


def _world_of_role(world: World, role: Role) -> list:
    return [
        world.agents[aid]
        for aid in world.agents_by_role.get(role, [])
        if aid in world.agents
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def distribute_to_producers(
    world: World,
    node_id: str,
    good: str,
    amount: int,
    exclude_agent_id: str | None = None,
) -> int:
    """Split `amount` gold across producer-role agents; prefer locals.

    Returns the amount actually distributed (==amount if a producer was found,
    0 if not — in which case the caller should redirect to node.gold).
    """
    if amount <= 0:
        return 0
    role = PRODUCER_OF.get(good)
    if role is None:
        return 0

    recipients = _locals_of_role(world, node_id, role)
    if not recipients:
        recipients = _world_of_role(world, role)
    if exclude_agent_id is not None:
        recipients = [a for a in recipients if a.id != exclude_agent_id]
    if not recipients:
        return 0

    n = len(recipients)
    per = amount // n
    remainder = amount - per * n
    for i, agent in enumerate(recipients):
        agent.gold += per + (1 if i < remainder else 0)
    return amount


def charge_consumers(
    world: World,
    node_id: str,
    good: str,
    amount: int,
    exclude_agent_id: str | None = None,
) -> int:
    """Collect `amount` gold from consumer-role agents at `node_id`.

    Tries primary consumer roles first; falls back to any co-located agent.
    Wealthier agents pay first. Returns the amount actually collected; any
    shortfall means insufficient consumer liquidity at this location.
    """
    if amount <= 0:
        return 0

    candidates: list = []
    preferred_roles = CONSUMER_OF.get(good, ())
    for role in preferred_roles:
        candidates.extend(_locals_of_role(world, node_id, role))

    if not candidates:
        candidates = [
            world.agents[aid]
            for aid in world.agents_by_node.get(node_id, [])
            if aid in world.agents
        ]

    if exclude_agent_id is not None:
        candidates = [a for a in candidates if a.id != exclude_agent_id]

    if not candidates:
        return 0

    candidates.sort(key=lambda a: getattr(a, "gold", 0), reverse=True)

    collected = 0
    remaining = amount
    for agent in candidates:
        if remaining <= 0:
            break
        pay = min(getattr(agent, "gold", 0), remaining)
        if pay <= 0:
            continue
        agent.gold -= pay
        collected += pay
        remaining -= pay
    return collected
