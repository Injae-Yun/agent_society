"""Merchant travel planning — route selection and next-hop logic."""

from __future__ import annotations

from agent_society.schema import Agent, NeedType, World
from agent_society.world import world as world_ops

# Node region labels for routing decisions
CITY_NODES = {"city.market", "city.smithy", "city.kitchen", "city.residential"}
FARM_NODES = {"farm.hub", "farm.grain_field", "farm.pasture", "farm.orchard", "farm.mine"}
RAIDER_NODES = {"raider.hideout"}

# Route mid-points (waypoints)
SAFE_MID = "route.safe_mid"
RISKY_MID = "route.risky_mid"

# Goods that flow city→farm vs farm→city
CITY_TO_FARM_GOODS = {"sword", "plow", "sickle", "pickaxe", "cooking_tools", "hammer", "cooked_meal"}
FARM_TO_CITY_GOODS = {"wheat", "meat", "fruit", "ore"}


def next_hop(agent: Agent, world: World) -> str | None:
    """Return the next node the merchant should move to, or None to stay."""
    cur = agent.current_node

    # Already at destination → clear and decide new direction
    if agent.travel_destination and cur == agent.travel_destination:
        agent.travel_destination = None

    # If no destination, choose one
    if agent.travel_destination is None:
        agent.travel_destination = _choose_destination(agent, world)

    if agent.travel_destination is None:
        return None

    return _route_aware_hop(agent, world, agent.travel_destination)


def _choose_destination(agent: Agent, world: World) -> str | None:
    """Decide whether merchant heads to farm.hub or city.market.

    Merchants never enter farm sub-nodes — they stop at farm.hub and interact
    with producers via 1-hop range collection / trade.
    """
    cur = agent.current_node

    if cur in CITY_NODES or cur == SAFE_MID or cur == RISKY_MID:
        return "farm.hub"

    if cur in FARM_NODES:
        return "city.market"

    return "city.market"


def _route_aware_hop(agent: Agent, world: World, destination: str) -> str | None:
    """Next hop with explicit safe/risky route selection.

    Armed merchants take the risky route (faster: 4 ticks).
    Unarmed merchants take the safe route (safer: 10 ticks).
    Within city or farmland sub-nodes, fall through to BFS.
    """
    cur = agent.current_node
    armed = should_use_risky_route(agent)
    mid = RISKY_MID if armed else SAFE_MID

    # ── Inter-region legs ────────────────────────────────────────────────────
    # City → Farm: must exit through city.market (the only city-route junction)
    if cur in CITY_NODES and destination in FARM_NODES:
        if cur != "city.market":
            return _next_hop_toward(agent, world, "city.market")
        return mid
    # At route mid heading to farm
    if cur == SAFE_MID and destination in FARM_NODES:
        return "farm.hub"
    if cur == RISKY_MID and destination in FARM_NODES:
        return "farm.hub"
    # Farm → City: must exit through farm.hub (the only farm-route junction)
    if cur in FARM_NODES and destination in CITY_NODES:
        if cur != "farm.hub":
            return _next_hop_toward(agent, world, "farm.hub")
        return mid
    # At route mid heading to city
    if cur == SAFE_MID and destination in CITY_NODES:
        return "city.market"
    if cur == RISKY_MID and destination in CITY_NODES:
        return "city.market"

    # ── Within same region: BFS ──────────────────────────────────────────────
    return _next_hop_toward(agent, world, destination)


def _next_hop_toward(agent: Agent, world: World, destination: str) -> str | None:
    """Find the next adjacent node toward destination via BFS."""
    cur = agent.current_node
    if cur == destination:
        return None

    # BFS over non-severed edges
    from collections import deque
    queue: deque[tuple[str, list[str]]] = deque()
    queue.append((cur, []))
    visited: set[str] = {cur}

    while queue:
        node_id, path = queue.popleft()
        for edge in world_ops.edges_from(world, node_id):
            neighbor = edge.v if edge.u == node_id else edge.u
            if neighbor in visited:
                continue
            visited.add(neighbor)
            new_path = path + [neighbor]
            if neighbor == destination:
                return new_path[0] if new_path else None
            queue.append((neighbor, new_path))

    return None


_RISKY_ARMED_THRESHOLD   = 0.55  # armed: use risky unless very scared
_RISKY_UNARMED_THRESHOLD = 0.10  # unarmed: only gamble when feeling very safe


def should_use_risky_route(agent: Agent) -> bool:
    """Route choice based on weapon status and safety need.

    Armed merchants take the risky (fast) route unless they're significantly
    scared (safety > 0.55).  After a major raid they'll play it safe for ~20
    ticks (0.4 spike / 0.010 decay = 40 ticks to 0; 0.4→0.55 is impossible so
    they switch to safe route until safety decays to 0.55 from 0.8 in ~25 ticks).

    Unarmed merchants very rarely gamble on the risky route when they feel
    completely safe (safety < 0.10) — occasional bold moves that put them in
    raider territory and create encounters that drive weapon purchases.
    """
    safety = agent.needs.get(NeedType.SAFETY, 0.0)
    if agent.has_usable_weapon():
        return safety < _RISKY_ARMED_THRESHOLD
    else:
        return safety < _RISKY_UNARMED_THRESHOLD


def has_goods_to_trade(agent: Agent) -> bool:
    """True if merchant is carrying tradeable goods."""
    return any(
        qty > 0 for good, qty in agent.inventory.items()
        if not good.startswith("_") and good in (FARM_TO_CITY_GOODS | CITY_TO_FARM_GOODS)
    )
