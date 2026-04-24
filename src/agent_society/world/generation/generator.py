"""generate_world — top-level procedural world builder (M7 integration).

Pipeline:
    1. Create empty hex grid + faction registry.
    2. Place settlements (capitals + villages + 1 landmark) at seeded anchors.
    3. Seed piece-bound NPC agents.
    4. Run `place_roads` over settlement centroids (civic/rural/rural mix).
    5. Drop a raider lair near the city-farthest village and trail it back
       to the road network.
    6. Assign Voronoi territory based on capital centroids.
    7. Noise-paint biomes on the remaining plains (and MOUNTAIN around
       the lair, road-preserving).
    8. Initialise agent hex positions.

`GenerationParams` controls the knobs. Deterministic by seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from agent_society.factions import DEFAULT_FACTIONS
from agent_society.schema import (
    Biome,
    Faction,
    HexTile,
    SettlementTier,
    World,
)
from agent_society.world.generation.biomes import DEFAULT_BIOME_WEIGHTS, assign_biomes
from agent_society.world.generation.lairs import LairPlacement, place_raider_lair
from agent_society.world.generation.risk import paint_raid_risk
from agent_society.world.generation.roads import RoadPlan, place_roads
from agent_society.world.generation.territory import assign_territory
from agent_society.world.pieces import PIECES, place_piece, seed_piece_agents
from agent_society.world.world import build_indices as _rebuild_indices
from agent_society.world.tiles import hex_within
from agent_society.world.world import build_indices


@dataclass
class GenerationParams:
    seed: int = 42
    map_half_size: int = 8
    capital_anchors: list[tuple[str, tuple[int, int], str]] = field(default_factory=lambda: [
        # (piece_id, (q, r), faction_id)
        ("capital_civic", (-5,  0), "civic"),
        ("capital_rural", ( 5,  1), "rural"),
    ])
    village_anchors: list[tuple[str, tuple[int, int], str]] = field(default_factory=lambda: [
        ("village_farm", ( 1, -3), "rural"),
        ("mining_camp",  (-2,  5), "rural"),
    ])
    landmark_anchors: list[tuple[str, tuple[int, int]]] = field(default_factory=lambda: [
        ("ancient_ruin", ( 4,  5)),
    ])
    biome_weights: dict[Biome, float] | None = None
    add_loop_edges: int = 1
    biome_cell_size: int = 3
    place_lair: bool = True
    lair_piece_id: str = "lair_outpost"


@dataclass
class GenerationReport:
    placements: list = field(default_factory=list)   # (piece, PlacementResult)
    road_plan: RoadPlan | None = None
    lair: LairPlacement | None = None
    biome_tally: dict[Biome, int] = field(default_factory=dict)


def generate_world(params: GenerationParams | None = None) -> tuple[World, GenerationReport]:
    """Build a world from scratch using `params`. Returns (world, report)."""
    params = params or GenerationParams()
    rng = Random(params.seed)
    report = GenerationReport()

    # ── 1. Empty grid + factions ────────────────────────────────────────────
    world = _empty_world(params.map_half_size)
    world.factions = {
        fid: Faction(f.id, f.name, f.home_region, f.hostile_by_default)
        for fid, f in DEFAULT_FACTIONS.items()
    }

    # ── 2. Place settlements ───────────────────────────────────────────────
    def _try_place(piece_id, anchor, faction, suffix):
        piece = PIECES[piece_id]
        anchor_tile = world.tiles.get(anchor)
        # Pre-paint biome so piece compat passes (for mining / etc.)
        if anchor_tile is not None and piece.biome_compat:
            if anchor_tile.biome not in piece.biome_compat:
                patch = _preferred_biome(piece.biome_compat)
                for coord in hex_within(anchor, 2):
                    t = world.tiles.get(coord)
                    if t is not None:
                        t.biome = patch
        result = place_piece(world, piece, anchor[0], anchor[1],
                             faction_id=faction, name_suffix=suffix)
        if not result.skipped:
            seed_piece_agents(world, result, piece, rng, faction_id=faction)
            report.placements.append((piece, result))
        return result

    city_node_ids: list[str] = []
    village_node_ids: list[str] = []
    capital_centroids: dict[str, list[tuple[int, int]]] = {}

    for i, (pid, anchor, faction) in enumerate(params.capital_anchors):
        res = _try_place(pid, anchor, faction, f"c{i+1}")
        if not res.skipped:
            city_node_ids.append(res.node_id)
            capital_centroids.setdefault(faction, []).append(anchor)

    for i, (pid, anchor, faction) in enumerate(params.village_anchors):
        res = _try_place(pid, anchor, faction, f"v{i+1}")
        if not res.skipped:
            village_node_ids.append(res.node_id)

    for i, (pid, anchor) in enumerate(params.landmark_anchors):
        _try_place(pid, anchor, None, f"l{i+1}")

    build_indices(world)

    # ── 4. Roads between settlements ────────────────────────────────────────
    road_nodes = city_node_ids + village_node_ids
    highway_pairs = {
        frozenset([a, b])
        for i, a in enumerate(city_node_ids)
        for b in city_node_ids[i + 1:]
    }
    report.road_plan = place_roads(
        world, road_nodes,
        highway_pairs=highway_pairs,
        add_loop_edges=params.add_loop_edges,
    )

    # ── 5. Raider lair + road trail + raider agent ─────────────────────────
    lair_hexes: list[tuple[int, int]] = []
    if params.place_lair and village_node_ids and city_node_ids:
        lair_piece = PIECES[params.lair_piece_id]
        lair_res = place_raider_lair(
            world, lair_piece,
            village_node_ids=village_node_ids,
            city_node_ids=city_node_ids,
            rng=rng,
            name_suffix="ridge",
        )
        report.lair = lair_res
        if not lair_res.skipped and lair_res.lair_hex is not None:
            lair_hexes.append(lair_res.lair_hex)
            # Seed the raider faction agent that lives at the lair.
            seed_piece_agents(
                world, lair_res.placement, lair_piece, rng,
                faction_id="raiders",
            )
            _rebuild_indices(world)   # raider just joined world.agents

    # ── 6. Voronoi territory (capitals as seeds) ────────────────────────────
    centroids_by_faction: dict[str, list[tuple[int, int]]] = dict(capital_centroids)
    if lair_hexes:
        centroids_by_faction.setdefault("raiders", []).extend(lair_hexes)
    assign_territory(world, centroids_by_faction)

    # ── 7. Biome noise ─────────────────────────────────────────────────────
    report.biome_tally = assign_biomes(
        world, Random(params.seed),
        weights=params.biome_weights or DEFAULT_BIOME_WEIGHTS,
        cell_size=params.biome_cell_size,
        lair_hexes=lair_hexes,
    )

    # ── 7b. Raid risk painting on nearby roads ─────────────────────────────
    if lair_hexes:
        paint_raid_risk(world, lair_hexes)

    # ── 8. Agent hex positions ─────────────────────────────────────────────
    for agent in world.agents.values():
        if agent.current_hex is None:
            node = world.nodes.get(agent.current_node)
            if node is not None and node.hex_q is not None:
                agent.current_hex = (node.hex_q, node.hex_r)
        if agent.current_hex is not None:
            agent.known_tiles.add(agent.current_hex)

    return world, report


# ── Internals ─────────────────────────────────────────────────────────────────

def _empty_world(half: int) -> World:
    tiles = {
        (q, r): HexTile(q=q, r=r, biome=Biome.PLAINS)
        for q in range(-half, half + 1)
        for r in range(-half, half + 1)
    }
    return World(nodes={}, edges=[], agents={}, tiles=tiles)


def _preferred_biome(compat: list[Biome]) -> Biome:
    """Pick a sensible default biome from a piece's compat list."""
    priority = [Biome.PLAINS, Biome.HILLS, Biome.FOREST, Biome.COAST,
                Biome.WASTELAND, Biome.MOUNTAIN]
    for b in priority:
        if b in compat:
            return b
    return compat[0]
