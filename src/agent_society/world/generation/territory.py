"""Voronoi territory assignment (M7b).

Each faction has one or more `centroids` (usually its capital cities). Every
tile on the map is assigned to the faction whose nearest centroid is closest
in hex distance. Ties broken by faction id for determinism.

Side effects:
    * writes `tile.owner_faction` for every tile
    * appends coords to `world.factions[fid].territory_tiles`
    * sets `world.factions[fid].territory_centroid` to the first centroid
      for display / later reference

A faction may be passed without centroids — it simply receives no tiles
(useful for raiders, who are tracked by lair hex not territory).
"""

from __future__ import annotations

from agent_society.schema import World
from agent_society.world.tiles import hex_distance


def assign_territory(
    world: World,
    centroids_by_faction: dict[str, list[tuple[int, int]]],
) -> None:
    """Paint `tile.owner_faction` across the whole grid via Voronoi-closest.

    Parameters
    ----------
    world
        World with a populated `tiles` grid and `factions` registry.
    centroids_by_faction
        Maps faction id → list of (q, r) centroids. Factions with an empty
        list (or missing entries) claim no tiles.
    """
    # Reset per-faction territory bookkeeping first.
    for fid, faction in world.factions.items():
        faction.territory_tiles = []
        centroids = centroids_by_faction.get(fid) or []
        faction.territory_centroid = centroids[0] if centroids else None

    # Flatten centroids with faction tag for the per-tile loop.
    flat: list[tuple[str, tuple[int, int]]] = []
    for fid, coords in centroids_by_faction.items():
        if fid not in world.factions:
            continue
        for c in coords:
            flat.append((fid, c))

    if not flat:
        return

    for coord, tile in world.tiles.items():
        best_fid: str | None = None
        best_dist = 10**9
        for fid, centroid in flat:
            d = hex_distance(coord, centroid)
            # Tie-break by fid for determinism.
            if d < best_dist or (d == best_dist and (best_fid is None or fid < best_fid)):
                best_dist = d
                best_fid = fid
        tile.owner_faction = best_fid
        if best_fid is not None:
            world.factions[best_fid].territory_tiles.append(coord)
