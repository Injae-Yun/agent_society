"""Raider lair placement tests (M7d)."""

from __future__ import annotations

from random import Random

from agent_society.schema import Biome, HexTile, Node, RegionType, RoadType, World
from agent_society.world.generation import place_raider_lair, place_roads
from agent_society.world.pieces import PIECES
from agent_society.world.world import build_indices


def _world_with_layout(coords: dict[str, tuple[int, int]]) -> World:
    """Plains grid + node per entry. Settlements are at the given hexes."""
    min_q = min(q for q, _ in coords.values()) - 5
    max_q = max(q for q, _ in coords.values()) + 5
    min_r = min(r for _, r in coords.values()) - 5
    max_r = max(r for _, r in coords.values()) + 5
    tiles = {
        (q, r): HexTile(q=q, r=r, biome=Biome.PLAINS)
        for q in range(min_q, max_q + 1)
        for r in range(min_r, max_r + 1)
    }
    nodes: dict[str, Node] = {}
    for nid, hx in coords.items():
        nodes[nid] = Node(id=nid, name=nid, region=RegionType.CITY,
                          hex_q=hx[0], hex_r=hx[1])
        tiles[hx].node_id = nid
    world = World(nodes=nodes, edges=[], agents={}, tiles=tiles)
    build_indices(world)
    return world


def test_picks_city_farthest_village():
    # Two villages — one near a city, one far.
    world = _world_with_layout({
        "city_A":    ( 0, 0),
        "village_near": ( 2, 0),        # 2 from city
        "village_far":  (10, 0),        # 10 from city
    })
    place_roads(world, ["city_A", "village_near", "village_far"])
    lair = PIECES["lair_outpost"]
    result = place_raider_lair(
        world, lair,
        village_node_ids=["village_near", "village_far"],
        city_node_ids=["city_A"],
        rng=Random(1),
    )
    assert not result.skipped, result.skipped_reason
    assert result.village_node_id == "village_far"
    # Lair should be near (within search radius) of the far village
    dist = abs(result.lair_hex[0] - 10) + abs(result.lair_hex[1])
    assert dist <= 8   # generous — search radius is 2..4 but hex distance differs


def test_lair_connected_to_road_via_new_path():
    world = _world_with_layout({
        "city":    ( 0, 0),
        "village": ( 8, 0),
    })
    # Build a baseline road city ↔ village
    road_plan = place_roads(world, ["city", "village"])
    baseline_road_tiles = {
        c for c, t in world.tiles.items() if t.road_type != RoadType.NONE
    }
    lair = PIECES["lair_outpost"]
    result = place_raider_lair(
        world, lair,
        village_node_ids=["village"],
        city_node_ids=["city"],
        rng=Random(2),
    )
    assert not result.skipped, result.skipped_reason
    # A road was laid
    assert result.junction_hex is not None
    assert result.junction_hex in baseline_road_tiles
    # All new tiles on the lair's path (excluding the junction) were previously
    # non-road and are now PATH.
    for coord in result.road_path:
        if coord == result.junction_hex:
            continue
        t = world.tiles[coord]
        if coord == result.lair_hex:
            # Lair tile itself stays WASTELAND biome, no road paint needed
            continue
        # Every new path tile should now be a PATH
        assert t.road_type in (RoadType.PATH, RoadType.HIGHWAY)


def test_lair_tile_is_wasteland():
    world = _world_with_layout({"city": (0, 0), "village": (8, 0)})
    place_roads(world, ["city", "village"])
    lair = PIECES["lair_outpost"]
    result = place_raider_lair(
        world, lair,
        village_node_ids=["village"],
        city_node_ids=["city"],
        rng=Random(3),
    )
    assert not result.skipped
    assert world.tiles[result.lair_hex].biome == Biome.WASTELAND
    assert world.tiles[result.lair_hex].node_id == result.placement.node_id


def test_connection_detours_around_existing_roads():
    """If the baseline road runs through the direct line, the lair's path
    should go around it, not over it."""
    world = _world_with_layout({"city": (0, 0), "village": (8, 0)})
    place_roads(world, ["city", "village"])   # paints straight line r=0
    # The baseline road is on all tiles (q, 0) for q ∈ [0..8]
    baseline = {(q, 0) for q in range(9)}
    lair = PIECES["lair_outpost"]
    result = place_raider_lair(
        world, lair,
        village_node_ids=["village"],
        city_node_ids=["city"],
        rng=Random(5),
    )
    assert not result.skipped
    # Tiles the lair laid down (path minus junction) should NOT overlap
    # baseline road tiles.
    for coord in result.road_path:
        if coord == result.junction_hex:
            continue
        assert coord not in baseline, (
            f"lair path tile {coord} overlaps baseline road"
        )
