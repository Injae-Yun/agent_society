"""Biome noise pass (M7b).

Strategy — deterministic *coarse-cell* biome assignment:
    1. Map the hex grid onto cells of size `cell_size` (default 3 hex per cell).
    2. For each cell, roll a weighted random biome. All tiles in that cell
       share the biome → natural blob-shaped regions without Perlin deps.
    3. Preserve tiles that were already meaningfully painted:
         - URBAN      (settlement / piece core)
         - WASTELAND  (lair core, stays dark)
         - any tile with a `node_id` (don't clobber landmarks)
         - any tile with `road_type != NONE` — roads stay on their native biome
    4. Post-process: for each lair hex, paint a radius-2 MOUNTAIN ring,
       excluding road tiles and node tiles (user spec — "산 배치, 도로 제외").

Designed to be idempotent-ish: re-running on a world already biomed just
re-rolls (seed-stable) the non-fixed tiles.
"""

from __future__ import annotations

from random import Random

from agent_society.schema import Biome, RoadType, World
from agent_society.world.tiles import hex_within


# Default weights across the temperate mainland. Sum → 1.0 (normalised).
DEFAULT_BIOME_WEIGHTS: dict[Biome, float] = {
    Biome.PLAINS:    0.40,
    Biome.FOREST:    0.25,
    Biome.HILLS:     0.15,
    Biome.MOUNTAIN:  0.08,
    Biome.WASTELAND: 0.08,
    Biome.COAST:     0.04,
}

_LAIR_MOUNTAIN_RADIUS = 2


def assign_biomes(
    world: World,
    rng: Random,
    *,
    weights: dict[Biome, float] | None = None,
    cell_size: int = 3,
    lair_hexes: list[tuple[int, int]] | None = None,
) -> dict[Biome, int]:
    """Paint biomes on non-fixed tiles. Returns a biome → count summary."""
    weights = dict(weights or DEFAULT_BIOME_WEIGHTS)
    _normalise_weights(weights)

    # 1. Coarse-cell assignment for non-fixed tiles
    cell_biomes: dict[tuple[int, int], Biome] = {}
    for coord, tile in world.tiles.items():
        if not _is_fixed(tile):
            cell = _cell_of(coord, cell_size)
            if cell not in cell_biomes:
                cell_biomes[cell] = _weighted_choice(rng, weights)
            tile.biome = cell_biomes[cell]

    # 2. Mountain ring around each lair (road-preserving, node-preserving)
    for lair in (lair_hexes or []):
        for coord in hex_within(lair, _LAIR_MOUNTAIN_RADIUS):
            tile = world.tiles.get(coord)
            if tile is None:
                continue
            if tile.road_type != RoadType.NONE:
                continue   # user spec: 도로 제외
            if tile.node_id is not None:
                continue   # don't clobber settlement / landmark / lair itself
            if tile.biome == Biome.WASTELAND:
                continue   # lair core stays WASTELAND
            tile.biome = Biome.MOUNTAIN

    # 3. Summary for logging / tests
    tally: dict[Biome, int] = {}
    for tile in world.tiles.values():
        tally[tile.biome] = tally.get(tile.biome, 0) + 1
    return tally


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_fixed(tile) -> bool:
    """Tile counts as 'fixed' (skip biome reassignment) if it carries a
    settlement / lair / road / node overlay."""
    if tile.node_id is not None:
        return True
    if tile.road_type != RoadType.NONE:
        return True
    if tile.biome in (Biome.URBAN, Biome.WASTELAND):
        return True
    return False


def _cell_of(coord: tuple[int, int], cell_size: int) -> tuple[int, int]:
    """Integer-division by cell_size — yields cluster id. Works for negative
    coords (Python's floor division is fine for Voronoi-style clustering)."""
    q, r = coord
    return (q // cell_size, r // cell_size)


def _normalise_weights(weights: dict[Biome, float]) -> None:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("biome weights must sum to a positive number")
    for k in list(weights):
        weights[k] /= total


def _weighted_choice(rng: Random, weights: dict[Biome, float]) -> Biome:
    """Normalised weights — pick one biome proportional to weight."""
    r = rng.random()
    acc = 0.0
    last = None
    for biome, w in weights.items():
        acc += w
        last = biome
        if r < acc:
            return biome
    return last   # floating-point safety net
