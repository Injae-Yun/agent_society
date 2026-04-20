"""WorldEvent type hierarchy — all events published on the WorldEventBus."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from agent_society.schema import RegionType


class EventSeverity(Enum):
    INFO = 0
    MINOR = 1
    MAJOR = 2
    CRITICAL = 3


@dataclass
class WorldEvent:
    tick: int
    source: str
    severity: EventSeverity
    duration: int = 0          # 0 = instantaneous
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def is_expired(self, current_tick: int) -> bool:
        if self.duration == 0:
            return True
        return current_tick >= self.tick + self.duration


# ── Natural / economic ───────────────────────────────────────────────────────

@dataclass
class HarvestBoom(WorldEvent):
    region: RegionType = RegionType.FARMLAND


@dataclass
class HarvestFailure(WorldEvent):
    region: RegionType = RegionType.FARMLAND


@dataclass
class PlagueOutbreak(WorldEvent):
    node: str = ""


@dataclass
class BulkOrder(WorldEvent):
    good: str = ""
    quantity: int = 0
    requester: str = ""


# ── Raider ───────────────────────────────────────────────────────────────────

@dataclass
class RaiderSurge(WorldEvent):
    delta_strength: float = 30.0


@dataclass
class RaiderDecline(WorldEvent):
    delta_strength: float = 30.0


@dataclass
class RaidAttempt(WorldEvent):
    target_node: str = ""
    result: Literal["repelled", "partial_loss", "plundered"] = "repelled"
    loot: dict[str, int] = field(default_factory=dict)


# ── Route ────────────────────────────────────────────────────────────────────

@dataclass
class RoadCollapse(WorldEvent):
    edge_u: str = ""
    edge_v: str = ""


@dataclass
class RoadRestored(WorldEvent):
    edge_u: str = ""
    edge_v: str = ""


# ── Quest / player ───────────────────────────────────────────────────────────

@dataclass
class GoldTax(WorldEvent):
    """유통 gold 과잉 시 징수 이벤트 — 인플레이션 억제."""
    tax_rate: float = 0.20    # agent gold의 이 비율을 징수


# ── Quest / player ───────────────────────────────────────────────────────────

@dataclass
class QuestAccepted(WorldEvent):
    quest_id: str = ""
    acceptor: str = ""


@dataclass
class QuestResolved(WorldEvent):
    quest_id: str = ""
    success: bool = False
