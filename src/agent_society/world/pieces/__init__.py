"""MapPiece library + placer (M7a).

A *piece* is a hand-designed cluster of hex tiles (settlement, raider lair,
landmark). The procedural map generator (M7c+) selects pieces from the
library by biome / faction compatibility and stamps them onto the world via
`place_piece()`.

Public API:
    from agent_society.world.pieces import PIECES, place_piece, seed_piece_agents
"""

from agent_society.world.pieces.library import PIECES, get_piece, pieces_by_kind
from agent_society.world.pieces.placer import (
    PlacementResult,
    can_place_piece,
    place_piece,
    seed_piece_agents,
)

__all__ = [
    "PIECES",
    "PlacementResult",
    "can_place_piece",
    "get_piece",
    "pieces_by_kind",
    "place_piece",
    "seed_piece_agents",
]
