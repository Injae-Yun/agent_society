"""Central data model — pure dataclasses only, no logic, no non-stdlib imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_society.events.types import WorldEvent


class Role(Enum):
    FARMER = "farmer"
    HERDER = "herder"
    MINER = "miner"
    ORCHARDIST = "orchardist"
    BLACKSMITH = "blacksmith"
    COOK = "cook"
    MERCHANT = "merchant"
    RAIDER = "raider"
    ADVENTURER = "adventurer"
    PLAYER = "player"


class RegionType(Enum):
    CITY = "city"
    FARMLAND = "farmland"
    RAIDER_BASE = "raider_base"
    ROUTE = "route"   # transit-only hex tiles on inter-region roads


# ── M7 hex terrain model ─────────────────────────────────────────────────────

class Biome(Enum):
    PLAINS    = "plains"
    HILLS     = "hills"
    FOREST    = "forest"
    MOUNTAIN  = "mountain"
    COAST     = "coast"
    WASTELAND = "wasteland"
    URBAN     = "urban"     # settlement piece hex


class RoadType(Enum):
    NONE    = 0
    PATH    = 1    # 시골길 — biome cost × 0.8
    HIGHWAY = 2    # 주요 도로 — biome cost × 0.5
    BRIDGE  = 3    # 강/협곡 통과 — biome cost 무시


class TileFeature(Enum):
    NONE   = "none"
    RIVER  = "river"
    RUINS  = "ruins"
    FORD   = "ford"
    SHRINE = "shrine"


class SettlementTier(Enum):
    HAMLET  = 1
    VILLAGE = 2
    TOWN    = 3
    CITY    = 4
    CAPITAL = 5


class Tier(Enum):
    BASIC = "basic"
    PREMIUM = "premium"


class NeedType(Enum):
    HUNGER = "hunger"
    FOOD_SATISFACTION = "food_satisfaction"
    TOOL_NEED = "tool_need"
    SAFETY = "safety"


@dataclass
class Item:
    type: str
    tier: Tier
    durability: float   # float — producers consume 0.01 per action
    max_durability: float

    def is_usable(self) -> bool:
        return self.durability > 0.0


@dataclass
class Node:
    id: str
    name: str
    region: RegionType
    stockpile: dict[str, int] = field(default_factory=dict)
    affordances: list[str] = field(default_factory=list)
    gold: int = 0   # node 내 유통 gold pool (소비·거래 수수료가 여기 쌓임)
    # Hex grid visualization fields
    hex_q: int | None = None      # axial column coordinate
    hex_r: int | None = None      # axial row coordinate
    cluster_id: str | None = None # "city" | "farm" — for 7-hex cluster rendering


@dataclass
class Edge:
    u: str
    v: str
    travel_cost: int
    base_threat: float = 0.0
    capacity: int = 1
    severed: bool = False


@dataclass
class Agent:
    id: str
    name: str
    role: Role
    home_node: str
    current_node: str
    needs: dict[NeedType, float] = field(default_factory=dict)
    inventory: dict[str, int] = field(default_factory=dict)
    tools: list[Item] = field(default_factory=list)
    equipped_weapon: Item | None = None
    # Tool durability tracker: {tool_type: float 0.0~max}
    tool_durability: dict[str, float] = field(default_factory=dict)
    # Travel state: destination and ticks remaining until arrival
    travel_destination: str | None = None   # current hop target (next node)
    travel_plan: str | None = None          # ultimate multi-hop goal (e.g. a hub)
    travel_ticks_remaining: int = 0   # >0 = in transit, decrement each tick
    gold: int = 0
    # M6 — faction membership + partial-knowledge reputation of the Player.
    faction_id: str | None = None
    known_player_rep: dict[str, float] = field(default_factory=dict)  # faction_id → -100..100
    # M7 — hex-grid position + hex-walking path + fog-of-war memory.
    current_hex: tuple[int, int] | None = None
    travel_path: list[tuple[int, int]] = field(default_factory=list)
    travel_step: int = 0
    known_tiles: set[tuple[int, int]] = field(default_factory=set)

    def has_usable_weapon(self) -> bool:
        return self.equipped_weapon is not None and self.equipped_weapon.is_usable()

    def get_tool_durability(self, tool_type: str, default: float = 10.0) -> float:
        return self.tool_durability.get(tool_type, default)

    def consume_tool(self, tool_type: str, amount: float = 0.01) -> float:
        """Reduce tool durability. Returns remaining durability."""
        current = self.tool_durability.get(tool_type, 10.0)
        updated = max(0.0, current - amount)
        self.tool_durability[tool_type] = updated
        return updated


@dataclass
class QuestIntent:
    id: str
    quest_type: str                  # bulk_delivery | raider_suppress | road_restore | escort
    target: str                      # node/edge/faction id
    urgency: float                   # 0.0 ~ 1.0
    supporters: list[str]            # 의뢰자 agent id 목록
    reward: dict[str, int]           # {"wheat": 10} — M3 이후 gold 포함
    quest_text: str                  # LLM 생성 서사
    status: str                      # pending | active | completed | expired
    issued_tick: int
    deadline_tick: int
    # M4 — who's doing the quest (adventurer or player) and who may take it.
    taker_id: str | None = None
    tier: str = "common"             # common (adventurer-eligible) | heroic (player-only)


@dataclass
class RaiderFaction(Agent):
    strength: float = 30.0  # 0 ~ 100


@dataclass
class AdventurerAgent(Agent):
    """NPC quest-taker. Competes with the PlayerAgent for pending quests."""
    skill: float = 50.0              # 0~100, affects quest progress speed & success
    combat_power: float = 20.0       # used when contributing to raider suppression
    active_quest_id: str | None = None
    quest_progress: float = 0.0      # 0.0 ~ 1.0, ticks-to-complete divided by duration


@dataclass
class PlayerAgent(AdventurerAgent):
    """The human-controlled agent. Uses the same quest machinery as Adventurer
    but its actions come from `PlayerInterface` input instead of utility AI.
    Eligible for `heroic`-tier quests that NPCs cannot take."""
    reputation: dict[str, float] = field(default_factory=dict)   # faction_id → -100..100
    quest_log: list[str] = field(default_factory=list)           # ids of completed quests
    pending_action: object | None = None                         # next PlayerAction to consume


@dataclass
class Faction:
    """A political/social bloc in the world. Agents belong to at most one.

    M6 scope: identity + home region + hostility default. Future expansions
    (treaties, wars, trade embargos) hang off this dataclass.
    """
    id: str
    name: str
    home_region: str                     # "city" | "farmland" | "raider_base" | ...
    hostile_by_default: bool = False     # raiders start at -40 with everyone
    # M7 — Voronoi territory over the hex grid (populated by MapGenerator).
    territory_centroid: tuple[int, int] | None = None
    territory_tiles: list[tuple[int, int]] = field(default_factory=list)


# ── M7 hex tiles + map pieces ────────────────────────────────────────────────

@dataclass
class HexTile:
    """Per-hex terrain background. Every hex in the playable map has one."""
    q: int
    r: int
    biome: "Biome" = field(default=None)                 # type: ignore[assignment]
    elevation: int = 0
    owner_faction: str | None = None
    road_type: "RoadType" = field(default=None)          # type: ignore[assignment]
    feature: "TileFeature" = field(default=None)         # type: ignore[assignment]
    node_id: str | None = None          # Node overlay, if any
    raid_risk: float = 0.0              # 0~1 — per-tick ambush probability for
                                        # merchants passing through

    def __post_init__(self) -> None:
        # Dataclass forward-ref defaults: assign real enum values at init.
        if self.biome is None:
            self.biome = Biome.PLAINS
        if self.road_type is None:
            self.road_type = RoadType.NONE
        if self.feature is None:
            self.feature = TileFeature.NONE


@dataclass
class PieceHex:
    """One hex inside a MapPiece template — offset from piece anchor."""
    dq: int
    dr: int
    biome: "Biome" = field(default=None)                 # type: ignore[assignment]
    role: str = "field"            # "center" | "gate" | "field" | "market" | ...
    is_gate: bool = False          # external road connection point

    def __post_init__(self) -> None:
        if self.biome is None:
            self.biome = Biome.URBAN


@dataclass
class MapPiece:
    """A pre-designed hex cluster: a settlement, raider lair, or landmark.

    Generator picks pieces matching biome/faction and stamps them onto
    the world's tile grid. Pieces with `spawns_node=True` also create a
    Node anchored at the piece centre.
    """
    id: str
    kind: str                               # "city" | "village" | "raider_lair" | "landmark"
    tier: SettlementTier
    hexes: list[PieceHex]
    biome_compat: list["Biome"] = field(default_factory=list)
    faction_eligibility: list[str] = field(default_factory=list)
    rarity: int = 1
    agent_seeds: list[dict] = field(default_factory=list)
    requires_road_adjacent: bool = False    # raider lairs are placed *after* roads
    spawns_node: bool = True
    is_landmark: bool = False               # shrine / ruin — Node created but
                                            # no agents seeded; quest-only interest


@dataclass
class World:
    nodes: dict[str, Node]
    edges: list[Edge]
    agents: dict[str, Agent]
    tick: int = 0
    active_events: list[WorldEvent] = field(default_factory=list)
    # Derived indices — rebuilt by world.py methods
    agents_by_node: dict[str, list[str]] = field(default_factory=dict)
    agents_by_role: dict[Role, list[str]] = field(default_factory=dict)
    # M6 — faction registry (id → Faction)
    factions: dict[str, Faction] = field(default_factory=dict)
    # M7 — dense hex-tile grid keyed by axial (q, r).
    tiles: dict[tuple[int, int], HexTile] = field(default_factory=dict)
