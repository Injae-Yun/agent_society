"""Starter piece library — 10 hand-designed clusters.

Each piece is a `MapPiece` whose `hexes` lists tiles by axial offset from
the piece anchor (the center hex). Roles within a piece (`role` field on
PieceHex) are descriptive — placer just copies them — but used downstream
for visualisation labels and agent seeding (e.g. "smithy" tile gets a
blacksmith).

`is_gate=True` marks the hex through which external roads should enter.
`requires_road_adjacent=True` (raider lairs) flags pieces that the
generator places after road computation.
"""

from __future__ import annotations

from agent_society.schema import Biome, MapPiece, PieceHex, SettlementTier


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ring1() -> list[tuple[int, int]]:
    """6 axial neighbours of (0, 0) — pointy-top hex ring 1."""
    return [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def _ring2() -> list[tuple[int, int]]:
    """12 axial neighbours of distance 2 from (0, 0) — ring 2."""
    return [
        (2, 0), (2, -1), (2, -2), (1, -2), (0, -2), (-1, -1),
        (-2, 0), (-2, 1), (-2, 2), (-1, 2), (0, 2), (1, 1),
    ]


# ── Piece definitions ────────────────────────────────────────────────────────

# 1. Capital city — civic capital, 13-hex (center + ring1 + 6 of ring2)
_capital_civic = MapPiece(
    id="capital_civic",
    kind="city",
    tier=SettlementTier.CAPITAL,
    hexes=(
        # center + inner ring (urban districts)
        [PieceHex(0, 0, Biome.URBAN, role="center")]
        + [PieceHex(dq, dr, Biome.URBAN,
                    role=("smithy" if (dq, dr) == (1, -1)
                          else "kitchen" if (dq, dr) == (0, -1)
                          else "market" if (dq, dr) == (1, 0)
                          else "guild" if (dq, dr) == (-1, 1)
                          else "lodge" if (dq, dr) == (-1, 0)
                          else "rest"))
           for dq, dr in _ring1()]
        # outer ring — gates + walls (PLAINS = farmland approaches)
        + [PieceHex(2, 0, Biome.PLAINS, role="gate", is_gate=True),
           PieceHex(0, -2, Biome.PLAINS, role="gate", is_gate=True),
           PieceHex(-2, 1, Biome.PLAINS, role="gate", is_gate=True),
           PieceHex(2, -2, Biome.PLAINS, role="orchard"),
           PieceHex(-2, 2, Biome.PLAINS, role="garden"),
           PieceHex(0, 2, Biome.PLAINS, role="approach")]
    ),
    biome_compat=[Biome.PLAINS, Biome.HILLS],
    faction_eligibility=["civic"],
    rarity=5,
    agent_seeds=[
        {"role": "blacksmith", "count": 3},
        {"role": "cook", "count": 3},
        {"role": "merchant", "count": 6},
        {"role": "adventurer", "count": 2},
    ],
)

# 2. Capital — agricultural alternative
_capital_rural = MapPiece(
    id="capital_rural",
    kind="city",
    tier=SettlementTier.CAPITAL,
    hexes=(
        [PieceHex(0, 0, Biome.URBAN, role="center")]
        + [PieceHex(dq, dr, Biome.URBAN if (dq, dr) in [(1, -1), (-1, 1)] else Biome.PLAINS,
                    role=("granary" if (dq, dr) == (1, -1)
                          else "market" if (dq, dr) == (-1, 1)
                          else "farmfield"),
                    is_gate=((dq, dr) in [(1, 0), (-1, 0)]))
           for dq, dr in _ring1()]
        + [PieceHex(2, -1, Biome.PLAINS, role="orchard"),
           PieceHex(-2, 1, Biome.PLAINS, role="orchard"),
           PieceHex(0, 2, Biome.PLAINS, role="pasture"),
           PieceHex(0, -2, Biome.PLAINS, role="pasture"),
           PieceHex(2, 0, Biome.PLAINS, role="approach"),
           PieceHex(-2, 2, Biome.PLAINS, role="approach")]
    ),
    biome_compat=[Biome.PLAINS, Biome.FOREST],
    faction_eligibility=["rural"],
    rarity=5,
    agent_seeds=[
        {"role": "farmer", "count": 5},
        {"role": "herder", "count": 4},
        {"role": "orchardist", "count": 3},
        {"role": "cook", "count": 2},
        {"role": "merchant", "count": 4},
    ],
)

# 3. Market town — mid-tier hub
_town_market = MapPiece(
    id="town_market",
    kind="town",
    tier=SettlementTier.TOWN,
    hexes=(
        [PieceHex(0, 0, Biome.URBAN, role="market")]
        + [PieceHex(dq, dr,
                    Biome.URBAN if (dq, dr) in [(1, 0), (0, -1)] else Biome.PLAINS,
                    role=("shop" if (dq, dr) == (1, 0)
                          else "smithy" if (dq, dr) == (0, -1)
                          else "field"),
                    is_gate=((dq, dr) in [(-1, 0), (0, 1)]))
           for dq, dr in _ring1()]
    ),
    biome_compat=[Biome.PLAINS, Biome.HILLS, Biome.FOREST],
    faction_eligibility=["civic", "rural"],
    rarity=3,
    agent_seeds=[
        {"role": "merchant", "count": 3},
        {"role": "blacksmith", "count": 1},
        {"role": "cook", "count": 1},
    ],
)

# 4. Farm village — spread of farmfield/pasture/orchard so each producer role
#    has its own hex slot to stand on (avoids dot pile-up).
_village_farm = MapPiece(
    id="village_farm",
    kind="village",
    tier=SettlementTier.VILLAGE,
    hexes=[
        PieceHex( 0,  0, Biome.URBAN,  role="center"),
        PieceHex( 1,  0, Biome.PLAINS, role="farmfield"),   # farmer
        PieceHex( 1, -1, Biome.PLAINS, role="farmfield"),   # farmer
        PieceHex( 0, -1, Biome.PLAINS, role="pasture"),     # herder
        PieceHex(-1,  0, Biome.PLAINS, role="pasture"),     # herder
        PieceHex(-1,  1, Biome.PLAINS, role="orchard"),     # spare role tag
        PieceHex( 0,  1, Biome.PLAINS, role="gate", is_gate=True),
    ],
    biome_compat=[Biome.PLAINS, Biome.FOREST],
    faction_eligibility=["rural"],
    rarity=2,
    agent_seeds=[
        {"role": "farmer", "count": 2},
        {"role": "herder", "count": 2},
    ],
)

# 5. Mining camp — small hills/mountain settlement
_mining_camp = MapPiece(
    id="mining_camp",
    kind="village",
    tier=SettlementTier.VILLAGE,
    hexes=[
        PieceHex(0, 0, Biome.URBAN, role="center"),
        PieceHex(1, 0, Biome.HILLS, role="mine"),
        PieceHex(0, -1, Biome.HILLS, role="mine"),
        PieceHex(-1, 0, Biome.HILLS, role="quarry"),
        PieceHex(0, 1, Biome.PLAINS, role="gate", is_gate=True),
    ],
    biome_compat=[Biome.HILLS, Biome.MOUNTAIN],
    faction_eligibility=["rural", "civic"],
    rarity=2,
    agent_seeds=[
        {"role": "miner", "count": 3},
    ],
)

# 6. Fishing village
_fishing_village = MapPiece(
    id="fishing_village",
    kind="village",
    tier=SettlementTier.VILLAGE,
    hexes=(
        [PieceHex(0, 0, Biome.URBAN, role="harbour")]
        + [PieceHex(dq, dr, Biome.COAST,
                    role="dock" if dq >= 0 else "boats")
           for dq, dr in _ring1()[:4]]
        + [PieceHex(0, 1, Biome.PLAINS, role="gate", is_gate=True)]
    ),
    biome_compat=[Biome.COAST],
    faction_eligibility=["civic"],
    rarity=2,
    agent_seeds=[
        {"role": "herder", "count": 2},  # placeholder — fishermen treated as herders for now
        {"role": "merchant", "count": 1},
    ],
)

# 7-10. Raider lairs — variable size, all `requires_road_adjacent`
_lair_outpost = MapPiece(
    id="lair_outpost",
    kind="raider_lair",
    tier=SettlementTier.HAMLET,
    hexes=[PieceHex(0, 0, Biome.WASTELAND, role="ambush")],
    biome_compat=[Biome.WASTELAND, Biome.FOREST],
    faction_eligibility=["raiders"],
    rarity=1,
    requires_road_adjacent=True,
    agent_seeds=[{"role": "raider", "count": 1}],
)

_lair_camp = MapPiece(
    id="lair_camp",
    kind="raider_lair",
    tier=SettlementTier.HAMLET,
    hexes=[
        PieceHex(0, 0, Biome.WASTELAND, role="center"),
        PieceHex(1, 0, Biome.WASTELAND, role="watch"),
        PieceHex(0, 1, Biome.WASTELAND, role="watch"),
    ],
    biome_compat=[Biome.WASTELAND, Biome.FOREST, Biome.MOUNTAIN],
    faction_eligibility=["raiders"],
    rarity=2,
    requires_road_adjacent=True,
    agent_seeds=[{"role": "raider", "count": 1}],
)

_lair_hideout = MapPiece(
    id="lair_hideout",
    kind="raider_lair",
    tier=SettlementTier.VILLAGE,
    hexes=(
        [PieceHex(0, 0, Biome.WASTELAND, role="center")]
        + [PieceHex(dq, dr, Biome.WASTELAND, role="watch")
           for dq, dr in _ring1()[:4]]
    ),
    biome_compat=[Biome.WASTELAND, Biome.MOUNTAIN],
    faction_eligibility=["raiders"],
    rarity=3,
    requires_road_adjacent=True,
    agent_seeds=[{"role": "raider", "count": 1}],
)

_lair_fortress = MapPiece(
    id="lair_fortress",
    kind="raider_lair",
    tier=SettlementTier.TOWN,
    hexes=(
        [PieceHex(0, 0, Biome.URBAN, role="keep")]
        + [PieceHex(dq, dr, Biome.WASTELAND, role="rampart")
           for dq, dr in _ring1()]
    ),
    biome_compat=[Biome.MOUNTAIN, Biome.WASTELAND],
    faction_eligibility=["raiders"],
    rarity=5,
    requires_road_adjacent=True,
    agent_seeds=[{"role": "raider", "count": 1}],
)

# 11-12. Landmarks — Node-bearing but no agents (quest target only)
_shrine = MapPiece(
    id="shrine",
    kind="landmark",
    tier=SettlementTier.HAMLET,
    hexes=[PieceHex(0, 0, Biome.PLAINS, role="shrine")],
    biome_compat=list(Biome),
    faction_eligibility=[],
    rarity=4,
    spawns_node=True,
    is_landmark=True,
    agent_seeds=[],
)

_ancient_ruin = MapPiece(
    id="ancient_ruin",
    kind="landmark",
    tier=SettlementTier.HAMLET,
    hexes=[
        PieceHex(0, 0, Biome.WASTELAND, role="ruin_center"),
        PieceHex(1, 0, Biome.WASTELAND, role="rubble"),
        PieceHex(0, 1, Biome.WASTELAND, role="rubble"),
    ],
    biome_compat=[Biome.WASTELAND, Biome.FOREST, Biome.HILLS],
    faction_eligibility=[],
    rarity=4,
    spawns_node=True,
    is_landmark=True,
    agent_seeds=[],
)


# ── Library registry ─────────────────────────────────────────────────────────

PIECES: dict[str, MapPiece] = {
    p.id: p for p in [
        _capital_civic, _capital_rural, _town_market, _village_farm,
        _mining_camp, _fishing_village,
        _lair_outpost, _lair_camp, _lair_hideout, _lair_fortress,
        _shrine, _ancient_ruin,
    ]
}


def get_piece(piece_id: str) -> MapPiece | None:
    return PIECES.get(piece_id)


def pieces_by_kind(kind: str) -> list[MapPiece]:
    return [p for p in PIECES.values() if p.kind == kind]
