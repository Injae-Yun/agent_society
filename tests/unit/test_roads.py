"""Road auto-generation tests (M7c)."""

from __future__ import annotations

from agent_society.schema import Biome, HexTile, Node, RegionType, RoadType, World
from agent_society.world.generation import place_roads
from agent_society.world.world import build_indices


def _world_with_settlements(coords: dict[str, tuple[int, int]]) -> World:
    """Build a minimal world: plains-only hex grid + node at each given hex."""
    min_q = min(q for q, _ in coords.values()) - 2
    max_q = max(q for q, _ in coords.values()) + 2
    min_r = min(r for _, r in coords.values()) - 2
    max_r = max(r for _, r in coords.values()) + 2

    tiles = {
        (q, r): HexTile(q=q, r=r, biome=Biome.PLAINS)
        for q in range(min_q, max_q + 1)
        for r in range(min_r, max_r + 1)
    }
    nodes = {
        nid: Node(id=nid, name=nid, region=RegionType.CITY,
                  hex_q=hx[0], hex_r=hx[1])
        for nid, hx in coords.items()
    }
    # Mark settlement tiles
    for nid, hx in coords.items():
        tiles[hx].node_id = nid

    world = World(nodes=nodes, edges=[], agents={}, tiles=tiles)
    build_indices(world)
    return world


def test_mst_connects_every_settlement():
    world = _world_with_settlements({
        "A": (0, 0), "B": (5, 0), "C": (2, -4), "D": (-3, 3),
    })
    plan = place_roads(world, list(world.nodes))
    # MST of 4 nodes → 3 edges
    assert len(plan.mst_edges) == 3
    assert plan.edge_count == 3
    # Every settlement appears in at least one MST edge
    seen: set[str] = set()
    for u, v in plan.mst_edges:
        seen.add(u)
        seen.add(v)
    assert seen == set(world.nodes)


def test_path_paints_road_tiles():
    world = _world_with_settlements({"A": (0, 0), "B": (5, 0)})
    place_roads(world, list(world.nodes))
    # At least some tiles between A and B should carry a PATH
    roaded = [t for t in world.tiles.values()
              if t.road_type != RoadType.NONE]
    assert len(roaded) >= 5, "expected A* to paint at least the straight 5-tile run"
    # Both endpoints should be roaded
    assert world.tiles[(0, 0)].road_type != RoadType.NONE
    assert world.tiles[(5, 0)].road_type != RoadType.NONE


def test_highway_upgrades_road_type():
    world = _world_with_settlements({"A": (0, 0), "B": (5, 0)})
    place_roads(world, list(world.nodes),
                highway_pairs={frozenset(["A", "B"])})
    # Centre hex along the straight path should be a HIGHWAY
    centre = world.tiles[(2, 0)]
    assert centre.road_type == RoadType.HIGHWAY


def test_loop_edges_add_beyond_mst():
    world = _world_with_settlements({
        "A": (0, 0), "B": (5, 0), "C": (2, -4), "D": (-3, 3),
    })
    plan = place_roads(world, list(world.nodes), add_loop_edges=2)
    assert len(plan.mst_edges) == 3
    assert len(plan.loop_edges) == 2
    assert plan.edge_count == 5


def test_logical_edges_appended_to_world():
    world = _world_with_settlements({"A": (0, 0), "B": (4, 0), "C": (2, 3)})
    before = len(world.edges)
    plan = place_roads(world, list(world.nodes))
    after = len(world.edges)
    assert after - before == plan.edge_count  # one Edge per MST+loop pair
    for e in world.edges[before:]:
        assert e.travel_cost >= 1


def test_skip_if_connected_does_not_duplicate_edges():
    from agent_society.schema import Edge
    world = _world_with_settlements({"A": (0, 0), "B": (4, 0)})
    world.edges.append(Edge("A", "B", travel_cost=4))
    place_roads(world, list(world.nodes))
    # Still just the single pre-existing edge between A and B
    ab_edges = [e for e in world.edges
                if frozenset([e.u, e.v]) == frozenset(["A", "B"])]
    assert len(ab_edges) == 1


def test_does_not_downgrade_existing_highway():
    world = _world_with_settlements({"A": (0, 0), "B": (5, 0)})
    # Pre-paint a HIGHWAY at the centre
    world.tiles[(2, 0)].road_type = RoadType.HIGHWAY
    place_roads(world, list(world.nodes))   # default PATH
    assert world.tiles[(2, 0)].road_type == RoadType.HIGHWAY
