"""Hex grid layout for the MVP world.

Coordinate system: pointy-top axial (q, r)
  Pixel:  x = S * √3 * (q + r/2)
          y = S * 3/2 * r         (y+ = screen down)

Layout (도안.png 기반):
  - City and Farm are single big-hex zones (centre + 6 neighbour slots).
  - Route tiles sit OUTSIDE the zones (at hex distance ≥ 2 from each centre).
  - Centre-to-centre distance: 7 hops
      = 1 (city→boundary) + 5 (boundary→boundary) + 1 (boundary→farm).
  - Route tile to its own end-zone is hex-dist 2 (the graph edge crosses the
    zone boundary hex visually); consecutive route tiles are hex-adjacent.

         risky.1  risky.2  risky.3  risky.4                (r = -2)
            ↘      ↕         ↕         ↙
  [CITY ──── boundary ────── hideout ──── boundary ──── FARM]    (r = -2 .. 0)
            ↗                              ↖
  safe.1 → safe.2 → ... → safe.7 → safe.8 → safe.9 → safe.10    (U, r = 1..3)
"""

from __future__ import annotations

# ── Route tile ID sequences (city→farm order) ────────────────────────────────

SAFE_ROUTE_IDS: list[str] = [f"route.safe.{i}" for i in range(1, 11)]   # 10 tiles
RISKY_ROUTE_IDS: list[str] = [f"route.risky.{i}" for i in range(1, 5)]  # 4 tiles

SAFE_TILE_SET: frozenset[str] = frozenset(SAFE_ROUTE_IDS)
RISKY_TILE_SET: frozenset[str] = frozenset(RISKY_ROUTE_IDS)
ALL_ROUTE_TILES: frozenset[str] = SAFE_TILE_SET | RISKY_TILE_SET

# ── Hex coordinates (axial q, r) ──────────────────────────────────────────────

HEX_COORDS: dict[str, tuple[int, int]] = {
    # ── Region centres ────────────────────────────────────────────────────────
    "city":           (0,   0),
    "farm":           (7,  -2),
    "raider.hideout": (3,   0),
    # ── Risky route (상단 직선, r = -2, all adjacent) ─────────────────────────
    "route.risky.1":  (2,  -2),   # adjacent to city boundary (1,-1)
    "route.risky.2":  (3,  -2),
    "route.risky.3":  (4,  -2),
    "route.risky.4":  (5,  -2),   # adjacent to farm boundary (6,-2)
    # ── Safe route (하단 U자, r = 1..3, all adjacent) ─────────────────────────
    "route.safe.1":  (-1,  2),    # adjacent to city boundary (-1,1)
    "route.safe.2":  (-1,  3),
    "route.safe.3":  ( 0,  3),
    "route.safe.4":  ( 1,  3),
    "route.safe.5":  ( 2,  3),
    "route.safe.6":  ( 3,  3),
    "route.safe.7":  ( 4,  3),
    "route.safe.8":  ( 5,  2),
    "route.safe.9":  ( 6,  1),
    "route.safe.10": ( 6,  0),    # adjacent to farm boundary (7,-1)
}

# ── Big-hex zones (centre + 6 adjacent slots, all free of route overlap) ─────

CITY_ZONE_HEXES: list[tuple[int, int]] = [
    (0, 0), (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1),
]
FARM_ZONE_HEXES: list[tuple[int, int]] = [
    (7, -2), (8, -2), (8, -3), (7, -3), (6, -2), (6, -1), (7, -1),
]

# Raider hideout — 5-hex blob centred at (3, 0); each member is adjacent to
# centre so the blob renders as one connected area. (3,-1) lies between the
# hideout and risky.3 so the visual edge reads naturally.
HIDEOUT_TERRITORY: list[tuple[int, int]] = [
    (3, -1), (3, 0), (4, 0), (3, 1), (3, 2), 
]

# Kept for html_renderer backward compatibility.
CLUSTER_HEXES: dict[str, list[tuple[int, int]]] = {
    "city": CITY_ZONE_HEXES,
    "farm": FARM_ZONE_HEXES,
}
CLUSTER_ID: dict[str, str] = {
    "city": "city",
    "farm": "farm",
}

# ── Role visual slots inside a zone ───────────────────────────────────────────
# All 6 neighbour slots of each zone are free (no route overlap), so every
# producer role gets its own hex.
#
# City (0,0):   NE=(1,-1)  N=(0,-1)  W=(-1,0)  SW=(-1,1)  S=(0,1)  E=(1,0)
# Farm (7,-2):  NE=(8,-3)  N=(7,-3)  W=(6,-2)  SW=(6,-1)  S=(7,-1) E=(8,-2)

ROLE_VISUAL_OFFSET: dict[tuple[str, str], tuple[int, int]] = {
    # ── City ─────────────────────────────────────────────────────────────────
    ("city", "blacksmith"):  (1, -1),  # NE — smithy
    ("city", "cook"):        (0, -1),  # N  — kitchen
    ("city", "merchant"):    (0,  0),  # market gate (centre)
    ("city", "adventurer"):  (-1, 1),  # SW — guild hall
    ("city", "player"):      (-1, 0),  # W  — adventurer's lodge (player starts here)
    # S (0,1) free for residential / future roles.
    # ── Farm ─────────────────────────────────────────────────────────────────
    ("farm", "farmer"):     (7, -3),   # N  — grain field
    ("farm", "herder"):     (8, -3),   # NE — pasture
    ("farm", "orchardist"): (6, -1),   # SW — orchard
    ("farm", "miner"):      (7, -1),   # S  — mine
    ("farm", "merchant"):   (7, -2),   # E  — hub gate
    # W (6,-2) free.
}


def visual_position(node_id: str, role: str) -> tuple[int, int]:
    """Return axial (q, r) for an agent given its logical node + role.

    For city/farm the role decides which zone neighbour the dot sits in.
    For route tiles and hideout the position is the node centre itself.
    Unknown nodes fall back to (0, 0).
    """
    key = (node_id, role)
    if key in ROLE_VISUAL_OFFSET:
        return ROLE_VISUAL_OFFSET[key]
    return HEX_COORDS.get(node_id, (0, 0))


# ── Hop distance from raider.hideout ─────────────────────────────────────────

HOPS_FROM_HIDEOUT: dict[str, int] = {
    "raider.hideout":  0,
    "route.risky.3":   1,   # directly connected to hideout (graph edge)
    "route.risky.2":   2,
    "route.risky.4":   2,
    "route.risky.1":   3,
}

# ── Per-tile ambush probability ───────────────────────────────────────────────

AMBUSH_PROB: dict[str, float] = {
    "route.risky.3": 0.65,   # 1 hop
    "route.risky.2": 0.40,   # 2 hops
    "route.risky.4": 0.40,
    "route.risky.1": 0.20,   # 3 hops
}

# ── Visual base_threat for edge colouring (HTML renderer only) ────────────────

VISUAL_THREAT: dict[str, float] = {
    # Safe tiles
    "route.safe.1":  0.02,
    "route.safe.2":  0.02,
    "route.safe.3":  0.02,
    "route.safe.4":  0.03,
    "route.safe.5":  0.03,
    "route.safe.6":  0.03,
    "route.safe.7":  0.03,
    "route.safe.8":  0.03,
    "route.safe.9":  0.02,
    "route.safe.10": 0.02,
    # Risky tiles (closer to hideout = more threat)
    "route.risky.1": 0.25,
    "route.risky.2": 0.55,
    "route.risky.3": 0.70,
    "route.risky.4": 0.45,
}
