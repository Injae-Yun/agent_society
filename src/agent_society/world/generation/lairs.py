"""Raider lair placement (M7d).

Rule (user spec):
  1. Pick the village-tier settlement farthest from any city-tier settlement.
  2. Drop a 1-hex lair piece near that village (on WASTELAND / non-road tile).
  3. Connect the lair to the **nearest existing road** with a *new* path that
     detours around other existing roads — raiders have their own back trail,
     they don't share the civic highway.
  4. (Follow-up, M7b) Terrain biome pass should paint MOUNTAIN around the
     lair area, excluding the road itself.

Returns a `LairPlacement` describing the placement + connection for logging.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from random import Random

from agent_society.schema import Biome, HexTile, MapPiece, RoadType, World
from agent_society.world.pieces import PlacementResult, place_piece
from agent_society.world.tiles import (
    a_star,
    hex_distance,
    hex_ring,
    tile_cost,
)


@dataclass
class LairPlacement:
    placement: PlacementResult | None
    village_node_id: str | None = None
    lair_hex: tuple[int, int] | None = None
    road_path: list[tuple[int, int]] = field(default_factory=list)
    junction_hex: tuple[int, int] | None = None
    skipped_reason: str = ""

    @property
    def skipped(self) -> bool:
        return self.placement is None or self.placement.skipped


# ── Public entry point ────────────────────────────────────────────────────────

def place_raider_lair(
    world: World,
    piece: MapPiece,
    *,
    village_node_ids: list[str],
    city_node_ids: list[str],
    rng: Random,
    faction_id: str = "raiders",
    name_suffix: str = "ridge",
    search_radius: tuple[int, int] = (2, 4),
    force_biome: Biome = Biome.WASTELAND,
) -> LairPlacement:
    """Place a lair near the city-farthest village, then road-connect it."""
    if not village_node_ids or not city_node_ids:
        return LairPlacement(placement=None, skipped_reason="no villages or cities")

    # ── 1. City-farthest village ─────────────────────────────────────────────
    city_hexes = [
        (world.nodes[cid].hex_q, world.nodes[cid].hex_r)
        for cid in city_node_ids
        if world.nodes.get(cid) is not None
        and world.nodes[cid].hex_q is not None
    ]
    if not city_hexes:
        return LairPlacement(placement=None, skipped_reason="no placed cities")

    def _city_distance(vid: str) -> int:
        v = world.nodes.get(vid)
        if v is None or v.hex_q is None:
            return 0
        vhex = (v.hex_q, v.hex_r)
        return min(hex_distance(vhex, ch) for ch in city_hexes)

    ranked = sorted(village_node_ids, key=_city_distance, reverse=True)
    target_vid = ranked[0]
    vnode = world.nodes[target_vid]
    vhex = (vnode.hex_q, vnode.hex_r)

    # ── 2. Candidate lair hexes — near village, not occupied, not road ───────
    lair_hex = _pick_lair_hex(world, piece, vhex, rng, search_radius)
    if lair_hex is None:
        return LairPlacement(
            placement=None, village_node_id=target_vid,
            skipped_reason=f"no compatible hex around {vhex}",
        )

    # Force biome to a lair-compatible value so place_piece's biome_compat
    # check passes.
    tile = world.tiles[lair_hex]
    if tile.biome not in piece.biome_compat:
        tile.biome = force_biome

    # ── 3. Place the lair piece ──────────────────────────────────────────────
    placement = place_piece(
        world, piece, lair_hex[0], lair_hex[1],
        faction_id=faction_id, name_suffix=name_suffix,
    )
    if placement.skipped:
        return LairPlacement(
            placement=placement, village_node_id=target_vid,
            lair_hex=lair_hex, skipped_reason=placement.reason,
        )

    # ── 4. Road connection — nearest existing road, avoid other roads ────────
    path, junction = _connect_to_road(world, lair_hex, placement.placed_hexes)
    # Paint only NEW tiles along the connection (don't touch existing roads).
    for coord in path:
        if coord == junction:
            break   # stop at junction — we're tapping in, not overwriting
        t = world.tiles.get(coord)
        if t is None:
            continue
        if t.road_type == RoadType.NONE:
            t.road_type = RoadType.PATH

    return LairPlacement(
        placement=placement,
        village_node_id=target_vid,
        lair_hex=lair_hex,
        road_path=path,
        junction_hex=junction,
    )


# ── Internals ─────────────────────────────────────────────────────────────────

def _pick_lair_hex(
    world: World,
    piece: MapPiece,
    village_hex: tuple[int, int],
    rng: Random,
    search_radius: tuple[int, int],
) -> tuple[int, int] | None:
    """Pick a hex near the village that is empty, not on a road, and either
    biome-compat with the lair piece or paint-able. Deterministic via `rng`."""
    lo, hi = search_radius
    # Pass 1 — strict: biome_compat match, no node, no road.
    strict_candidates: list[tuple[int, int]] = []
    relaxed_candidates: list[tuple[int, int]] = []
    for radius in range(lo, hi + 1):
        for coord in hex_ring(village_hex, radius):
            t = world.tiles.get(coord)
            if t is None:
                continue
            if t.node_id is not None:
                continue
            if t.road_type != RoadType.NONE:
                continue
            if math.isinf(tile_cost(t)):
                continue
            if t.biome in piece.biome_compat:
                strict_candidates.append(coord)
            relaxed_candidates.append(coord)
        if strict_candidates:
            break

    pool = strict_candidates or relaxed_candidates
    if not pool:
        return None
    return rng.choice(pool)


def _connect_to_road(
    world: World,
    lair_hex: tuple[int, int],
    lair_placed: list[tuple[int, int]],
) -> tuple[list[tuple[int, int]], tuple[int, int] | None]:
    """A* from `lair_hex` to the nearest existing road tile, routing around
    OTHER road tiles with a heavy penalty so raiders forge a fresh trail.
    Returns (path, junction_hex) — junction is the first existing-road hex
    the path hits."""
    # Collect existing roads (not the lair's own freshly stamped tiles).
    road_tiles = [
        coord for coord, t in world.tiles.items()
        if t.road_type != RoadType.NONE and coord not in lair_placed
    ]
    if not road_tiles:
        return [], None

    junction = min(road_tiles, key=lambda c: hex_distance(lair_hex, c))

    # Penalty for stepping onto any existing road *other* than the goal.
    _ROAD_DETOUR_PENALTY = 50.0

    def _avoid_other_roads(coord: tuple[int, int], tile: HexTile) -> float:
        if coord == junction:
            return 0.0
        if tile.road_type != RoadType.NONE:
            return _ROAD_DETOUR_PENALTY
        return 0.0

    path = a_star(world.tiles, lair_hex, junction,
                  extra_cost=_avoid_other_roads)
    return (path or []), junction
