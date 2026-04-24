"""place_piece — stamp a MapPiece onto the world's tile grid.

Each call:
  1. Translates the piece's PieceHex offsets to absolute (q, r) tile coords.
  2. Updates each tile's biome / owner_faction in place (creates tile if
     the target hex is outside the existing grid — generators sometimes
     stamp pieces near the boundary).
  3. If `piece.spawns_node` is True, creates a Node at the piece centre
     (the hex with role=='center', falling back to the anchor hex), and
     marks the tile with `node_id`.
  4. `seed_piece_agents()` is a separate helper used by procedural builders
     (M7d) — placement and agent spawning are decoupled so generators can
     decide population independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from agent_society.economy.config import (
    MERCHANT_INITIAL_GOLD,
    PRODUCER_INITIAL_GOLD,
)
from agent_society.factions import role_to_faction
from agent_society.schema import (
    AdventurerAgent,
    Agent,
    HexTile,
    MapPiece,
    Node,
    PieceHex,
    RaiderFaction,
    RegionType,
    Role,
    World,
)


# Map piece.kind → RegionType for the spawned Node (legacy compatibility).
_KIND_REGION: dict[str, RegionType] = {
    "city":         RegionType.CITY,
    "town":         RegionType.CITY,
    "village":      RegionType.FARMLAND,
    "raider_lair":  RegionType.RAIDER_BASE,
    "landmark":     RegionType.ROUTE,
}

# Affordances handed to the spawned Node, keyed by piece.kind.
_KIND_AFFORDANCES: dict[str, list[str]] = {
    "city":        ["trade", "craft_weapons", "craft_tools", "cook", "rest"],
    "town":        ["trade", "craft_tools"],
    "village":     ["trade", "produce_wheat", "produce_meat"],
    "raider_lair": ["raider_spawn"],
    "landmark":    [],
}

# Map an agent role → list of acceptable PieceHex `role` tags. Agents are
# spread across hexes whose role tag matches; if no match, they fall back to
# the piece centre.  This keeps a 13-hex city's agents visually spread out
# instead of all stacked on the same dot.
ROLE_TO_TILE_ROLES: dict[str, list[str]] = {
    "blacksmith": ["smithy", "forge"],
    "cook":       ["kitchen", "granary"],
    "merchant":   ["market", "shop", "gate", "harbour", "approach"],
    "farmer":     ["farmfield", "field", "approach"],
    "herder":     ["pasture", "stockyard"],
    "orchardist": ["orchard", "garden"],
    "miner":      ["mine", "quarry"],
    "adventurer": ["guild", "lodge"],
    "raider":     ["watch", "ambush", "rampart", "keep", "center"],
    "player":     ["lodge", "guild"],
}


def _role_slots(piece, placed_hexes: list[tuple[int, int]]) -> dict[str, list[tuple[int, int]]]:
    """Map agent role.value → list of hex coords whose tile role tag matches."""
    out: dict[str, list[tuple[int, int]]] = {}
    # piece.hexes is parallel to placed_hexes (set by place_piece)
    for ph, coord in zip(piece.hexes, placed_hexes):
        for agent_role, tile_roles in ROLE_TO_TILE_ROLES.items():
            if ph.role in tile_roles:
                out.setdefault(agent_role, []).append(coord)
    return out


@dataclass
class PlacementResult:
    """Summary of a single place_piece call — useful for the generator log."""
    piece_id: str
    anchor: tuple[int, int]
    placed_hexes: list[tuple[int, int]]
    node_id: str | None = None
    spawned_agents: list[str] = field(default_factory=list)
    skipped: bool = False
    reason: str = ""


# ── Pre-flight: can the piece fit here? ───────────────────────────────────────

def can_place_piece(
    world: World,
    piece: MapPiece,
    anchor_q: int,
    anchor_r: int,
    *,
    allow_overlap: bool = False,
) -> tuple[bool, str]:
    """Check if `piece` can be stamped at `(anchor_q, anchor_r)` on the world.

    Without `allow_overlap`, refuses if any target hex already has a Node.
    Always refuses if the anchor's tile biome is not in `piece.biome_compat`
    (when the anchor tile exists).
    """
    anchor_tile = world.tiles.get((anchor_q, anchor_r))
    if anchor_tile is not None and piece.biome_compat:
        if anchor_tile.biome not in piece.biome_compat:
            return False, f"biome mismatch ({anchor_tile.biome.value} not in compat)"

    for ph in piece.hexes:
        coord = (anchor_q + ph.dq, anchor_r + ph.dr)
        existing = world.tiles.get(coord)
        if existing is not None and existing.node_id is not None and not allow_overlap:
            return False, f"overlap at {coord} (node {existing.node_id})"
    return True, "ok"


# ── Stamp ─────────────────────────────────────────────────────────────────────

def place_piece(
    world: World,
    piece: MapPiece,
    anchor_q: int,
    anchor_r: int,
    *,
    faction_id: str | None = None,
    name_suffix: str = "",
    allow_overlap: bool = False,
) -> PlacementResult:
    """Stamp the piece onto world.tiles + create a Node (if applicable)."""
    ok, reason = can_place_piece(world, piece, anchor_q, anchor_r,
                                 allow_overlap=allow_overlap)
    if not ok:
        return PlacementResult(
            piece_id=piece.id, anchor=(anchor_q, anchor_r),
            placed_hexes=[], skipped=True, reason=reason,
        )

    placed: list[tuple[int, int]] = []
    center_coord = (anchor_q, anchor_r)

    for ph in piece.hexes:
        coord = (anchor_q + ph.dq, anchor_r + ph.dr)
        tile = world.tiles.get(coord)
        if tile is None:
            tile = HexTile(q=coord[0], r=coord[1], biome=ph.biome)
            world.tiles[coord] = tile
        else:
            tile.biome = ph.biome
        if faction_id is not None:
            tile.owner_faction = faction_id
        if ph.role == "center":
            center_coord = coord
        placed.append(coord)

    # Spawn a Node anchored at the centre hex if the piece declares one.
    node_id: str | None = None
    if piece.spawns_node:
        suffix = f"_{name_suffix}" if name_suffix else ""
        node_id = f"{piece.id}{suffix}"
        # Avoid collision with an existing node id.
        if node_id in world.nodes:
            i = 2
            while f"{node_id}_{i}" in world.nodes:
                i += 1
            node_id = f"{node_id}_{i}"
        node = Node(
            id=node_id,
            name=f"{piece.kind.title()} {name_suffix}".strip() or piece.id,
            region=_KIND_REGION.get(piece.kind, RegionType.ROUTE),
            affordances=list(_KIND_AFFORDANCES.get(piece.kind, [])),
            hex_q=center_coord[0],
            hex_r=center_coord[1],
            cluster_id=piece.id,
        )
        world.nodes[node_id] = node
        center_tile = world.tiles.get(center_coord)
        if center_tile is not None:
            center_tile.node_id = node_id

    return PlacementResult(
        piece_id=piece.id,
        anchor=(anchor_q, anchor_r),
        placed_hexes=placed,
        node_id=node_id,
    )


# ── Agent seeding (used by generator, optional for hand-place) ────────────────

def seed_piece_agents(
    world: World,
    placement: PlacementResult,
    piece: MapPiece,
    rng: Random,
    faction_id: str | None = None,
    id_prefix: str | None = None,
) -> list[str]:
    """Spawn agents per `piece.agent_seeds`, homed at placement.node_id and
    visually distributed across role-matching hexes within the piece."""
    if placement.node_id is None:
        return []
    # Landmarks never seed agents — even if agent_seeds is populated it'd be
    # meaningless (quest-target only). Raider lairs DO seed agents (raiders
    # are flagged is_landmark=False).
    if piece.is_landmark:
        return []
    home = placement.node_id
    spawned: list[str] = []
    prefix = id_prefix or placement.node_id

    slots = _role_slots(piece, placement.placed_hexes)
    fallback_hex: tuple[int, int] | None = (
        placement.placed_hexes[0] if placement.placed_hexes else None
    )

    for seed in piece.agent_seeds:
        try:
            role = Role(seed["role"])
        except ValueError:
            continue
        count_spec = seed.get("count", 1)
        count = (rng.randint(*count_spec) if isinstance(count_spec, (list, tuple))
                 else int(count_spec))
        fid = faction_id or role_to_faction(role)
        role_slots = slots.get(role.value, [])
        for i in range(count):
            aid = f"{prefix}_{role.value}_{i + 1}"
            if aid in world.agents:
                continue
            agent = _make_agent(aid, role, home, fid)
            # Spread agents across matching role hexes (round-robin); fall back
            # to the piece anchor if no role-tagged tile exists in this piece.
            chosen_hex = (role_slots[i % len(role_slots)] if role_slots
                          else fallback_hex)
            if chosen_hex is not None:
                agent.current_hex = chosen_hex
                agent.known_tiles.add(chosen_hex)
            world.agents[aid] = agent
            placement.spawned_agents.append(aid)
            spawned.append(aid)
    return spawned


def _make_agent(aid: str, role: Role, home: str, faction_id: str | None) -> Agent:
    if role == Role.RAIDER:
        return RaiderFaction(
            id=aid, name=aid, role=role,
            home_node=home, current_node=home,
            faction_id=faction_id, strength=30.0,
        )
    if role == Role.ADVENTURER:
        return AdventurerAgent(
            id=aid, name=aid, role=role,
            home_node=home, current_node=home,
            faction_id=faction_id,
            gold=60, skill=50.0, combat_power=20.0,
        )
    gold = (MERCHANT_INITIAL_GOLD if role == Role.MERCHANT
            else PRODUCER_INITIAL_GOLD)
    return Agent(
        id=aid, name=aid, role=role,
        home_node=home, current_node=home,
        faction_id=faction_id, gold=gold,
    )
