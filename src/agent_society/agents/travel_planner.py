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
    """Return the next node the merchant should move to, or None to stay."""
    cur = agent.current_node

    # Already at destination → clear and decide new direction
    if agent.travel_destination and cur == agent.travel_destination:
        agent.travel_destination = None

    # If no destination, choose one
    if agent.travel_destination is None:
        agent.travel_destination = _choose_destination(agent)

    if agent.travel_destination is None:
        return None

    return _route_aware_hop(agent, world, agent.travel_destination)


def _choose_destination(agent: Agent) -> str | None:
    """Decide whether merchant heads to farm or city."""
    cur = agent.current_node
    if cur == FARM_NODE:
        return CITY_NODE
    # From city, route tiles, or anywhere else default to farm.
    return FARM_NODE


def _route_aware_hop(agent: Agent, world: World, destination: str) -> str | None:
    """Next hop with explicit safe/risky route selection.

    Route choice is made when entering from city or farm. Once on a route,
    continue along it to the far end. Armed merchants prefer the risky route;
    unarmed prefer safe.
    """
    cur = agent.current_node
    armed = should_use_risky_route(agent)

    # ── City → Farm: enter a route from the city side ────────────────────────
    if cur == CITY_NODE and destination == FARM_NODE:
        return RISKY_ROUTE_IDS[0] if armed else SAFE_ROUTE_IDS[0]

    # ── Farm → City: enter a route from the far end ──────────────────────────
    if cur == FARM_NODE and destination == CITY_NODE:
        return RISKY_ROUTE_IDS[-1] if armed else SAFE_ROUTE_IDS[-1]

    # ── On safe route ────────────────────────────────────────────────────────
    if cur in SAFE_TILE_SET:
        idx = SAFE_ROUTE_IDS.index(cur)
        if destination == FARM_NODE:
            return SAFE_ROUTE_IDS[idx + 1] if idx + 1 < len(SAFE_ROUTE_IDS) else FARM_NODE
        if destination == CITY_NODE:
            return SAFE_ROUTE_IDS[idx - 1] if idx > 0 else CITY_NODE

    # ── On risky route ───────────────────────────────────────────────────────
    if cur in RISKY_TILE_SET:
        idx = RISKY_ROUTE_IDS.index(cur)
        if destination == FARM_NODE:
            return RISKY_ROUTE_IDS[idx + 1] if idx + 1 < len(RISKY_ROUTE_IDS) else FARM_NODE
        if destination == CITY_NODE:
            return RISKY_ROUTE_IDS[idx - 1] if idx > 0 else CITY_NODE

    # ── Fallback: BFS ────────────────────────────────────────────────────────
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
