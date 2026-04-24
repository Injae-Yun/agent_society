"""Hex tile helpers — axial math, A* routing, biome/road cost model.

The world is now a dense `dict[(q, r)] → HexTile`. Agents traverse the grid
step-by-step along A*-computed paths; edges on World.edges are *logical*
connections between Nodes, not the movement graph itself.

Movement cost model:
    base_cost(biome)            # 1.0 plains, 1.5 hills/forest, 3.0 mountain …
    road_multiplier(road_type)  # 0.5 highway, 0.8 path, 1.0 none
    => tile_cost = base × multiplier
Impassable biomes (Biome.COAST without a bridge, etc.) emit math.inf.
"""

from __future__ import annotations

import heapq
import math

from agent_society.schema import Biome, HexTile, RoadType


# ── Axial / cube hex math ─────────────────────────────────────────────────────

# Pointy-top axial neighbours — matches hex_map.py rendering.
_AXIAL_DIRS = [
    ( 1,  0), ( 1, -1), ( 0, -1),
    (-1,  0), (-1,  1), ( 0,  1),
]


def neighbors(q: int, r: int) -> list[tuple[int, int]]:
    return [(q + dq, r + dr) for dq, dr in _AXIAL_DIRS]


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Axial distance in hex steps."""
    aq, ar = a
    bq, br = b
    dq, dr = aq - bq, ar - br
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def hex_ring(center: tuple[int, int], radius: int) -> list[tuple[int, int]]:
    """All hexes exactly `radius` steps from `center`."""
    if radius <= 0:
        return [center]
    results: list[tuple[int, int]] = []
    q, r = center[0] + _AXIAL_DIRS[4][0] * radius, center[1] + _AXIAL_DIRS[4][1] * radius
    for i in range(6):
        for _ in range(radius):
            results.append((q, r))
            q += _AXIAL_DIRS[i][0]
            r += _AXIAL_DIRS[i][1]
    return results


def hex_within(center: tuple[int, int], radius: int) -> list[tuple[int, int]]:
    """All hexes within `radius` steps (including center)."""
    out = [center]
    for k in range(1, radius + 1):
        out.extend(hex_ring(center, k))
    return out


# ── Movement cost tables ──────────────────────────────────────────────────────

_BIOME_COST: dict[Biome, float] = {
    Biome.PLAINS:    1.0,
    Biome.HILLS:     1.5,
    Biome.FOREST:    1.4,
    Biome.MOUNTAIN:  3.0,
    Biome.COAST:     2.5,
    Biome.WASTELAND: 1.8,
    Biome.URBAN:     0.9,        # paved streets
}

_ROAD_MULT: dict[RoadType, float] = {
    # Strong bias — off-road is 5× slower, so A* only deviates when the
    # shortest legitimate road is clearly longer than cutting through wilds.
    RoadType.NONE:    5.0,
    RoadType.PATH:    1.0,
    RoadType.HIGHWAY: 0.6,
    RoadType.BRIDGE:  0.8,
}


def tile_cost(tile: HexTile) -> float:
    """Movement cost to enter this tile. ∞ means impassable."""
    base = _BIOME_COST.get(tile.biome, 1.0)
    mult = _ROAD_MULT.get(tile.road_type, 1.0)
    # Coast without a bridge/ford is impassable for now.
    if tile.biome == Biome.COAST and tile.road_type not in (RoadType.BRIDGE,):
        return math.inf
    return base * mult


# ── A* path finding ───────────────────────────────────────────────────────────

def a_star(
    tiles: dict[tuple[int, int], HexTile],
    start: tuple[int, int],
    goal: tuple[int, int],
    max_expand: int = 20_000,
    extra_cost: "callable | None" = None,
) -> list[tuple[int, int]] | None:
    """Shortest hex path from start to goal on the current tile grid.

    Returns a list of hex coords including start and goal, or None if no
    route exists. Heuristic = hex_distance * min_biome_cost (admissible).

    `extra_cost(coord, tile) -> float` lets a caller add a penalty on top of
    the base tile cost — used e.g. by lair road-laying to detour around
    existing roads.
    """
    if start == goal:
        return [start]
    if start not in tiles or goal not in tiles:
        return None

    min_cost = min(_BIOME_COST.values()) * min(_ROAD_MULT.values())
    open_heap: list[tuple[float, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0.0, start))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start: 0.0}
    expanded = 0

    while open_heap and expanded < max_expand:
        _, current = heapq.heappop(open_heap)
        if current == goal:
            return _reconstruct(came_from, current)
        expanded += 1

        for nbr in neighbors(*current):
            nbr_tile = tiles.get(nbr)
            if nbr_tile is None:
                continue
            cost = tile_cost(nbr_tile)
            if extra_cost is not None:
                cost += extra_cost(nbr, nbr_tile)
            if math.isinf(cost):
                continue
            tentative = g_score[current] + cost
            if tentative < g_score.get(nbr, math.inf):
                came_from[nbr] = current
                g_score[nbr] = tentative
                f = tentative + hex_distance(nbr, goal) * min_cost
                heapq.heappush(open_heap, (f, nbr))

    return None


def path_cost(tiles: dict[tuple[int, int], HexTile],
              path: list[tuple[int, int]]) -> float:
    """Sum of tile_cost for every step except the start hex."""
    if not path or len(path) < 2:
        return 0.0
    total = 0.0
    for coord in path[1:]:
        tile = tiles.get(coord)
        if tile is None:
            total += math.inf
            break
        total += tile_cost(tile)
    return total


def _reconstruct(came_from: dict, end: tuple[int, int]) -> list[tuple[int, int]]:
    path = [end]
    while end in came_from:
        end = came_from[end]
        path.append(end)
    path.reverse()
    return path


# ── Fog-of-war helpers ────────────────────────────────────────────────────────

def reveal_area(
    known: set[tuple[int, int]],
    center: tuple[int, int],
    radius: int,
    tiles: dict[tuple[int, int], HexTile] | None = None,
) -> int:
    """Add hexes within `radius` of `center` to `known`. Returns # new tiles."""
    added = 0
    for h in hex_within(center, radius):
        if tiles is not None and h not in tiles:
            continue
        if h not in known:
            known.add(h)
            added += 1
    return added
