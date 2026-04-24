"""Merchant travel planning — route selection and next-hop logic."""

from __future__ import annotations

from agent_society.schema import Agent, NeedType, World
from agent_society.world import world as world_ops
from agent_society.world.hex_map import (
    RISKY_ROUTE_IDS,
    RISKY_TILE_SET,
    SAFE_ROUTE_IDS,
    SAFE_TILE_SET,
)

CITY_NODE = "city"
FARM_NODE = "farm"
RAIDER_HIDEOUT = "raider.hideout"

# Goods that flow city→farm vs farm→city
CITY_TO_FARM_GOODS = {"sword", "plow", "sickle", "pickaxe", "cooking_tools", "hammer", "cooked_meal"}
FARM_TO_CITY_GOODS = {"wheat", "meat", "fruit", "ore"}


def next_hop(agent: Agent, world: World) -> str | None:
    """Return the next node the merchant should move to, or None to stay.

    Uses `agent.travel_plan` to persist the merchant's ultimate hub target
    across multiple hops. `travel_destination` tracks only the current hop's
    target (a route tile or the hub), so arriving on a route tile doesn't
    flip the plan back toward the origin.

    Supports both the legacy mvp_scenario (hard-coded city/farm + route tiles)
    and procedurally generated worlds (any node carrying the "trade" affordance
    is a valid hub).
    """
    cur = agent.current_node

    # Reset plan when the merchant has reached its ultimate hub.
    if agent.travel_plan and cur == agent.travel_plan:
        agent.travel_plan = None

    # Pick a new hub if we aren't heading to one yet.
    if agent.travel_plan is None:
        agent.travel_plan = _choose_destination(agent, world)

    if agent.travel_plan is None or agent.travel_plan == cur:
        return None

    return _route_aware_hop(agent, world, agent.travel_plan)


def _choose_destination(agent: Agent, world: World) -> str | None:
    """Pick the merchant's next hub. Covers legacy + procedural worlds."""
    cur = agent.current_node

    # Legacy mvp scenario — hard-wired city ↔ farm.
    if CITY_NODE in world.nodes and FARM_NODE in world.nodes:
        if cur == FARM_NODE:
            return CITY_NODE
        if cur == CITY_NODE:
            return FARM_NODE
        # On a route tile → continue toward whichever hub the agent's home
        # ISN'T (merchants default to "visit the other hub").
        if agent.home_node == FARM_NODE:
            return CITY_NODE
        return FARM_NODE

    # Procedural: bounce between home and a partner hub. Partner is stable
    # per merchant (hash(agent.id) mod N) so routes stay predictable.
    home = agent.home_node
    trade_hubs = [
        nid for nid, n in world.nodes.items()
        if "trade" in n.affordances and nid != home
    ]
    if not trade_hubs:
        return None
    if cur == home:
        # Head out to the designated partner.
        partner = trade_hubs[abs(hash(agent.id)) % len(trade_hubs)]
        return partner
    # Elsewhere → come home.
    return home


def _route_aware_hop(agent: Agent, world: World, destination: str) -> str | None:
    """Next hop toward `destination`.

    Legacy mvp_scenario path: explicit safe/risky route selection (armed
    merchants prefer risky). Procedural world path: the destination itself
    is the next hop — TravelAction computes the full A* hex path, and the
    merchant walks it.
    """
    cur = agent.current_node
    armed = should_use_risky_route(agent)

    legacy_layout = CITY_NODE in world.nodes and FARM_NODE in world.nodes
    if legacy_layout:
        # City → Farm: enter a route from the city side
        if cur == CITY_NODE and destination == FARM_NODE:
            return RISKY_ROUTE_IDS[0] if armed else SAFE_ROUTE_IDS[0]
        # Farm → City: enter a route from the far end
        if cur == FARM_NODE and destination == CITY_NODE:
            return RISKY_ROUTE_IDS[-1] if armed else SAFE_ROUTE_IDS[-1]
        # On safe route → next safe tile
        if cur in SAFE_TILE_SET:
            idx = SAFE_ROUTE_IDS.index(cur)
            if destination == FARM_NODE:
                return SAFE_ROUTE_IDS[idx + 1] if idx + 1 < len(SAFE_ROUTE_IDS) else FARM_NODE
            if destination == CITY_NODE:
                return SAFE_ROUTE_IDS[idx - 1] if idx > 0 else CITY_NODE
        # On risky route → next risky tile
        if cur in RISKY_TILE_SET:
            idx = RISKY_ROUTE_IDS.index(cur)
            if destination == FARM_NODE:
                return RISKY_ROUTE_IDS[idx + 1] if idx + 1 < len(RISKY_ROUTE_IDS) else FARM_NODE
            if destination == CITY_NODE:
                return RISKY_ROUTE_IDS[idx - 1] if idx > 0 else CITY_NODE

    # Procedural worlds (or legacy fallback): the destination node itself is
    # the hop target; TravelAction's A* figures out the hex route.
    if destination in world.nodes:
        return destination
    return _next_hop_toward(agent, world, destination)


def _next_hop_toward(agent: Agent, world: World, destination: str) -> str | None:
    """Find the next adjacent node toward destination via BFS."""
    cur = agent.current_node
    if cur == destination:
        return None

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


_RISKY_ARMED_THRESHOLD   = 0.75  # armed: use risky unless safety > 0.75 (very scared)
_RISKY_UNARMED_THRESHOLD = 0.15  # unarmed: only gamble when feeling fairly safe


def should_use_risky_route(agent: Agent) -> bool:
    """Route choice based on weapon status and safety need."""
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
