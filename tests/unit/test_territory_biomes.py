"""Territory Voronoi + biome noise tests (M7b)."""

from __future__ import annotations

from random import Random

from agent_society.factions import DEFAULT_FACTIONS
from agent_society.schema import (
    Biome,
    Faction,
    HexTile,
    RoadType,
    World,
)
from agent_society.world.generation import (
    assign_biomes,
    assign_territory,
    generate_world,
    GenerationParams,
)


def _plain_world(half: int = 4) -> World:
    tiles = {
        (q, r): HexTile(q=q, r=r, biome=Biome.PLAINS)
        for q in range(-half, half + 1)
        for r in range(-half, half + 1)
    }
    factions = {fid: Faction(f.id, f.name, f.home_region, f.hostile_by_default)
                for fid, f in DEFAULT_FACTIONS.items()}
    return World(nodes={}, edges=[], agents={}, tiles=tiles, factions=factions)


# ── Territory ────────────────────────────────────────────────────────────────

def test_territory_voronoi_closest_centroid():
    world = _plain_world(4)
    assign_territory(world, {
        "civic":   [(-4, 0)],
        "rural":   [( 4, 0)],
    })
    # Left side should be civic, right side should be rural.
    assert world.tiles[(-4, 0)].owner_faction == "civic"
    assert world.tiles[( 4, 0)].owner_faction == "rural"
    assert world.tiles[(-2, 0)].owner_faction == "civic"
    assert world.tiles[( 2, 0)].owner_faction == "rural"


def test_territory_updates_faction_bookkeeping():
    world = _plain_world(3)
    assign_territory(world, {
        "civic": [(0, 0)],
    })
    # Every tile claimed by civic
    total = sum(1 for t in world.tiles.values() if t.owner_faction == "civic")
    assert total == len(world.tiles)
    assert world.factions["civic"].territory_centroid == (0, 0)
    assert len(world.factions["civic"].territory_tiles) == len(world.tiles)


def test_territory_empty_centroids_no_assignment():
    world = _plain_world(2)
    assign_territory(world, {"civic": []})
    # No centroids → no tile is owned
    assert all(t.owner_faction is None for t in world.tiles.values())


# ── Biome noise ──────────────────────────────────────────────────────────────

def test_biome_noise_is_deterministic_with_seed():
    w1 = _plain_world(5)
    w2 = _plain_world(5)
    assign_biomes(w1, Random(42))
    assign_biomes(w2, Random(42))
    for coord in w1.tiles:
        assert w1.tiles[coord].biome == w2.tiles[coord].biome


def test_biome_noise_preserves_urban_and_roads():
    world = _plain_world(5)
    world.tiles[(0, 0)].biome = Biome.URBAN
    world.tiles[(1, 0)].biome = Biome.WASTELAND
    world.tiles[(2, 0)].road_type = RoadType.PATH
    world.tiles[(2, 0)].biome = Biome.PLAINS   # road on plains
    assign_biomes(world, Random(5))
    assert world.tiles[(0, 0)].biome == Biome.URBAN
    assert world.tiles[(1, 0)].biome == Biome.WASTELAND
    # Road tile biome should be untouched (we preserve so the road doesn't
    # suddenly sit on mountains).
    assert world.tiles[(2, 0)].biome == Biome.PLAINS


def test_mountain_ring_around_lair_excludes_roads():
    world = _plain_world(5)
    # Place a "road" tile directly next to our pretend lair hex.
    world.tiles[(1, 0)].road_type = RoadType.PATH
    world.tiles[(1, 0)].biome = Biome.PLAINS
    # Fake lair hex
    lair_hex = (0, 0)
    world.tiles[lair_hex].biome = Biome.WASTELAND

    assign_biomes(world, Random(0), lair_hexes=[lair_hex])

    # Lair itself stays WASTELAND
    assert world.tiles[lair_hex].biome == Biome.WASTELAND
    # Road tile stays on its original biome (PLAINS here), not MOUNTAIN
    assert world.tiles[(1, 0)].biome == Biome.PLAINS
    # At least one nearby non-road, non-lair tile should be MOUNTAIN
    mountain_nearby = any(
        world.tiles[(q, r)].biome == Biome.MOUNTAIN
        for (q, r) in [(-1, 0), (0, -1), (0, 1), (-1, 1), (1, -1)]
        if (q, r) in world.tiles
    )
    assert mountain_nearby


# ── generate_world pipeline ──────────────────────────────────────────────────

def test_generate_world_produces_connected_map():
    world, report = generate_world(GenerationParams(seed=42))
    # Nodes created
    assert len(world.nodes) >= 4   # 2 capitals + 2 villages + 1 landmark
    # Tiles populated
    assert len(world.tiles) > 0
    # Roads exist
    assert report.road_plan is not None and report.road_plan.edge_count > 0
    # Lair placed
    assert report.lair is not None
    assert not report.lair.skipped
    # Biome variety — at least 3 different biomes in the output
    biomes_present = {t.biome for t in world.tiles.values()}
    assert len(biomes_present) >= 3
    # Territory assignments — every non-border tile claimed
    claimed = sum(1 for t in world.tiles.values() if t.owner_faction is not None)
    assert claimed == len(world.tiles)


def test_generate_world_is_deterministic():
    w1, r1 = generate_world(GenerationParams(seed=99))
    w2, r2 = generate_world(GenerationParams(seed=99))
    # Same biome tally across two runs with identical seeds
    assert r1.biome_tally == r2.biome_tally
    # Same settlement count
    assert len(w1.nodes) == len(w2.nodes)
    # Same lair position
    assert r1.lair.lair_hex == r2.lair.lair_hex
