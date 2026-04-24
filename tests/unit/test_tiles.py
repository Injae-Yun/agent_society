"""Hex math + A* path-finding tests."""

from __future__ import annotations

import math

from agent_society.schema import Biome, HexTile, RoadType
from agent_society.world.tiles import (
    a_star,
    hex_distance,
    hex_within,
    neighbors,
    path_cost,
    reveal_area,
    tile_cost,
)


def _flat_grid(min_q: int, max_q: int, min_r: int, max_r: int,
               biome: Biome = Biome.PLAINS) -> dict[tuple[int, int], HexTile]:
    return {
        (q, r): HexTile(q=q, r=r, biome=biome)
        for q in range(min_q, max_q + 1)
        for r in range(min_r, max_r + 1)
    }


def test_neighbors_returns_six():
    n = neighbors(0, 0)
    assert len(n) == 6
    assert (1, 0) in n and (-1, 0) in n
    assert (0, 1) in n and (0, -1) in n


def test_hex_distance_axial():
    assert hex_distance((0, 0), (3, 0)) == 3
    assert hex_distance((0, 0), (0, 3)) == 3
    assert hex_distance((0, 0), (-2, -2)) == 4
    assert hex_distance((1, 1), (1, 1)) == 0


def test_hex_within_includes_centre():
    h = hex_within((0, 0), 1)
    assert (0, 0) in h
    assert len(h) == 7  # centre + 6 neighbours


def test_tile_cost_road_discount():
    plain = HexTile(0, 0, Biome.PLAINS, road_type=RoadType.NONE)
    paved = HexTile(0, 0, Biome.PLAINS, road_type=RoadType.HIGHWAY)
    assert tile_cost(paved) < tile_cost(plain)


def test_tile_cost_coast_impassable_without_bridge():
    coast = HexTile(0, 0, Biome.COAST, road_type=RoadType.NONE)
    bridge = HexTile(0, 0, Biome.COAST, road_type=RoadType.BRIDGE)
    assert math.isinf(tile_cost(coast))
    assert not math.isinf(tile_cost(bridge))


def test_a_star_finds_straight_path():
    tiles = _flat_grid(-2, 5, -2, 2)
    path = a_star(tiles, (0, 0), (4, 0))
    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (4, 0)
    # straight line on uniform plains = 5 tiles (incl. start & end)
    assert len(path) == 5


def test_a_star_routes_around_impassable():
    tiles = _flat_grid(-2, 5, -2, 2)
    # Wall of coast across the middle column — only bridges allow crossing,
    # so the path must detour above or below.
    for r in (-1, 0, 1):
        tiles[(2, r)] = HexTile(2, r, Biome.COAST, road_type=RoadType.NONE)
    path = a_star(tiles, (0, 0), (4, 0))
    assert path is not None
    # No tile in the path should be the impassable wall
    for coord in path:
        t = tiles[coord]
        if t.biome == Biome.COAST:
            assert t.road_type == RoadType.BRIDGE


def test_a_star_returns_none_when_unreachable():
    tiles = _flat_grid(-1, 1, -1, 1)
    # Surround the start with coast — no path out.
    for c in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]:
        tiles[c] = HexTile(*c, Biome.COAST)
    assert a_star(tiles, (0, 0), (5, 0)) is None


def test_path_cost_sums_steps_excluding_start():
    tiles = _flat_grid(-1, 3, -1, 1)
    path = a_star(tiles, (0, 0), (3, 0))
    cost = path_cost(tiles, path)
    # 3 steps × 1.0 (PLAINS) × 5.0 (off-road penalty) = 15.0
    assert cost == 15.0


def test_reveal_area_adds_within_radius():
    known: set[tuple[int, int]] = set()
    added = reveal_area(known, (0, 0), 1)
    assert added == 7              # centre + 6 neighbours
    assert (0, 0) in known
    assert (1, 0) in known


def test_reveal_area_skips_missing_tiles():
    tiles = _flat_grid(0, 1, 0, 0)   # only (0,0) and (1,0) exist
    known: set[tuple[int, int]] = set()
    reveal_area(known, (0, 0), 1, tiles)
    # Only existing tiles should be revealed
    assert known == {(0, 0), (1, 0)}


def test_hex_walking_travel_advances_one_hex_per_tick():
    """Integration: TravelAction produces a path; society ticks it forward."""
    from random import Random
    from agent_society.agents.actions import TravelAction
    from agent_society.agents.society import AgentSociety
    from agent_society.events.bus import WorldEventBus
    from agent_society.schema import Agent, Edge, Node, RegionType, Role, World
    from agent_society.world.world import build_indices

    nodes = {
        "a": Node("a", "A", RegionType.CITY, hex_q=0, hex_r=0),
        "b": Node("b", "B", RegionType.CITY, hex_q=3, hex_r=0),
    }
    tiles = {(q, r): HexTile(q, r, Biome.PLAINS) for q in range(-1, 5) for r in range(-1, 2)}
    tiles[(0, 0)].node_id = "a"
    tiles[(3, 0)].node_id = "b"
    agent = Agent("a1", "Alice", Role.MERCHANT, "a", "a", current_hex=(0, 0))
    world = World(
        nodes=nodes, edges=[Edge("a", "b", travel_cost=1)],
        agents={"a1": agent}, tiles=tiles,
    )
    build_indices(world)

    # Kick off travel
    TravelAction(agent=agent, target_node="b").execute(world, WorldEventBus())
    assert agent.travel_path
    initial_len = len(agent.travel_path)
    assert agent.current_node == "a"   # not arrived yet

    # Walk through ticks until arrival
    society = AgentSociety(bus=WorldEventBus(), rng=Random(1))
    for _ in range(initial_len):
        society._advance_travel(agent, world)

    assert agent.current_node == "b"
    assert agent.current_hex == (3, 0)
    assert agent.travel_path == []
