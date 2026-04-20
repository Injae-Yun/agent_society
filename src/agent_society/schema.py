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


class RegionType(Enum):
    CITY = "city"
    FARMLAND = "farmland"
    RAIDER_BASE = "raider_base"


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
    travel_destination: str | None = None
    travel_ticks_remaining: int = 0   # >0 = in transit, decrement each tick
    gold: int = 0

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


@dataclass
class RaiderFaction(Agent):
    strength: float = 30.0  # 0 ~ 100


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
