"""MapPiece library + placer tests."""

from __future__ import annotations

from random import Random

from agent_society.schema import Biome, HexTile, RoadType, World
from agent_society.world.pieces import (
    PIECES,
    can_place_piece,
    get_piece,
    pieces_by_kind,
    place_piece,
    seed_piece_agents,
)
from agent_society.world.world import build_indices


def _empty_world(size: int = 10) -> World:
    tiles = {
        (q, r): HexTile(q=q, r=r, biome=Biome.PLAINS)
        for q in range(-size, size + 1)
        for r in range(-size, size + 1)
    }
    return World(nodes={}, edges=[], agents={}, tiles=tiles)


def test_library_loaded():
    assert "capital_civic" in PIECES
    assert "village_farm" in PIECES
    assert "lair_hideout" in PIECES
    # Ensure each piece has at least one hex
    for pid, piece in PIECES.items():
        assert len(piece.hexes) >= 1, f"piece {pid} has no hexes"


def test_pieces_by_kind_groups_correctly():
    cities = pieces_by_kind("city")
    villages = pieces_by_kind("village")
    lairs = pieces_by_kind("raider_lair")
    assert all(p.kind == "city" for p in cities)
    assert all(p.kind == "village" for p in villages)
    assert all(p.kind == "raider_lair" for p in lairs)
    assert len(lairs) >= 3       # outpost / camp / hideout / fortress


def test_place_piece_stamps_tiles_and_node():
    world = _empty_world()
    village = get_piece("village_farm")
    res = place_piece(world, village, 0, 0, faction_id="rural", name_suffix="alpha")
    assert not res.skipped
    assert res.node_id is not None
    # Centre hex carries the node
    assert world.tiles[(0, 0)].node_id == res.node_id
    # Node registered in the world
    node = world.nodes[res.node_id]
    assert node.hex_q == 0 and node.hex_r == 0
    # All piece hexes inherited the faction owner
    for coord in res.placed_hexes:
        assert world.tiles[coord].owner_faction == "rural"


def test_place_piece_refuses_overlap_by_default():
    world = _empty_world()
    village = get_piece("village_farm")
    first = place_piece(world, village, 0, 0, name_suffix="first")
    assert not first.skipped, f"first placement failed: {first.reason}"
    res2 = place_piece(world, village, 0, 0, name_suffix="second")
    # The second attempt either fails on biome mismatch (anchor turned URBAN
    # after the first stamp) or on overlap with the existing node — both are
    # valid "you can't drop a village on top of another" outcomes.
    assert res2.skipped
    assert any(s in res2.reason for s in ("overlap", "biome"))


def test_place_piece_biome_compat_check():
    world = _empty_world()
    # Force the anchor tile to be COAST — capital_civic isn't compatible
    world.tiles[(0, 0)] = HexTile(0, 0, Biome.COAST)
    res = place_piece(world, get_piece("capital_civic"), 0, 0)
    assert res.skipped
    assert "biome mismatch" in res.reason


def test_seed_piece_agents_spawns_per_count():
    world = _empty_world()
    village = get_piece("village_farm")
    res = place_piece(world, village, 0, 0, faction_id="rural", name_suffix="north")
    spawned = seed_piece_agents(world, res, village, Random(1), faction_id="rural")
    # village_farm has 2 farmers + 2 herders (post-M7a-fix; spread over role tiles)
    assert len(spawned) == 4
    farmers = [aid for aid in spawned if "farmer" in aid]
    herders = [aid for aid in spawned if "herder" in aid]
    assert len(farmers) == 2
    assert len(herders) == 2
    # All agents homed at the new node
    for aid in spawned:
        assert world.agents[aid].home_node == res.node_id


def test_seed_piece_agents_distributes_across_role_hexes():
    """Agents should be assigned to hexes whose role tag matches their job."""
    world = _empty_world()
    village = get_piece("village_farm")
    res = place_piece(world, village, 0, 0, faction_id="rural", name_suffix="x")
    spawned = seed_piece_agents(world, res, village, Random(1), faction_id="rural")
    farmer_hexes = {world.agents[aid].current_hex
                    for aid in spawned if "farmer" in aid}
    herder_hexes = {world.agents[aid].current_hex
                    for aid in spawned if "herder" in aid}
    # 2 farmers should land on the 2 farmfield hexes; same for herders/pasture
    assert len(farmer_hexes) >= 1   # at least one matched slot
    assert len(herder_hexes) >= 1
    # No farmer should be sitting on the village center (anchor) — they have
    # dedicated farmfield tiles to occupy.
    assert all(hx != (0, 0) for hx in farmer_hexes)


def test_landmark_has_node_but_no_agents():
    world = _empty_world()
    shrine = get_piece("shrine")
    res = place_piece(world, shrine, 5, -2, name_suffix="east")
    assert res.node_id is not None
    spawned = seed_piece_agents(world, res, shrine, Random(1))
    assert spawned == []   # landmark = no agent seeding


def test_lair_outpost_is_single_hex_and_road_required():
    lair = get_piece("lair_outpost")
    assert len(lair.hexes) == 1
    assert lair.requires_road_adjacent is True
    world = _empty_world()
    # Lair compat = WASTELAND/FOREST — set the anchor accordingly first.
    world.tiles[(0, 0)] = HexTile(0, 0, Biome.WASTELAND)
    res = place_piece(world, lair, 0, 0, faction_id="raiders")
    assert not res.skipped, res.reason
    assert res.placed_hexes == [(0, 0)]
    assert world.tiles[(0, 0)].biome == Biome.WASTELAND


def test_can_place_piece_outside_existing_tiles_creates_them():
    """Stamping a piece partially outside the grid extends the grid."""
    world = _empty_world(size=2)   # tight 5x5 grid
    village = get_piece("village_farm")
    # Place at edge — some hexes will be outside the initial grid
    res = place_piece(world, village, 2, 0, faction_id="rural")
    assert not res.skipped
    # Newly created hexes are present
    assert (3, 0) in world.tiles
    assert (2, -1) in world.tiles
