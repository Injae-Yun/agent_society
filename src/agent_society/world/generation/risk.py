"""Raid-risk painting — per-tile ambush probability derived from lair distance.

A road tile's `raid_risk` is the per-tick probability that a merchant
passing through is ambushed. The value tapers linearly with hex distance
to the nearest raider lair:

    risk(d) = max(0, base - falloff · d)    (d = hex_distance to lair)

Default: base=0.15, falloff=0.025 → 0 at d ≥ 6. A 3-hex-deep danger
zone gives ~39% cumulative ambush chance, which is memorable but not
oppressive.

If multiple lairs are present, each tile takes the **maximum** of all
per-lair risks (dangerous valleys overlap).

Only tiles with `road_type != NONE` get risk; wilderness already costs
5× off-road under the new tile_cost, so raiders don't bother staking out
forests that merchants wouldn't cross anyway.
"""

from __future__ import annotations

from agent_society.schema import RoadType, World
from agent_society.world.tiles import hex_distance


DEFAULT_RISK_BASE = 0.15
DEFAULT_RISK_FALLOFF = 0.025
DEFAULT_RISK_MAX_DIST = 6


def paint_raid_risk(
    world: World,
    lair_hexes: list[tuple[int, int]],
    *,
    base: float = DEFAULT_RISK_BASE,
    falloff: float = DEFAULT_RISK_FALLOFF,
    max_dist: int = DEFAULT_RISK_MAX_DIST,
) -> int:
    """Stamp `raid_risk` on road tiles within `max_dist` of any lair.
    Returns the number of tiles affected."""
    if not lair_hexes:
        return 0
    touched = 0
    for coord, tile in world.tiles.items():
        if tile.road_type == RoadType.NONE:
            continue
        best = 0.0
        for lair_hex in lair_hexes:
            d = hex_distance(coord, lair_hex)
            if d > max_dist:
                continue
            risk = max(0.0, base - falloff * d)
            if risk > best:
                best = risk
        if best > tile.raid_risk:
            tile.raid_risk = round(best, 3)
            touched += 1
    return touched
