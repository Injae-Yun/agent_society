"""needs + world state → QuestIntent 생성 로직."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from agent_society.config.parameters import QUEST_REFRESH_INTERVAL, URGENCY_THRESHOLD
from agent_society.schema import NeedType, QuestIntent, Role

if TYPE_CHECKING:
    from agent_society.schema import World
    from agent_society.world.snapshot import WorldSnapshot

_NEED_TO_QUEST: dict[NeedType, str] = {
    NeedType.HUNGER: "bulk_delivery",
    NeedType.FOOD_SATISFACTION: "bulk_delivery",
    NeedType.TOOL_NEED: "bulk_delivery",
    NeedType.SAFETY: "raider_suppress",
}

_NEED_TO_TARGET: dict[NeedType, str] = {
    NeedType.HUNGER: "wheat",
    NeedType.FOOD_SATISFACTION: "cooked_meal",
    NeedType.TOOL_NEED: "ore",
    NeedType.SAFETY: "raider",
}

# 퀘스트 타입별 기본 보상 재화
_BASE_REWARD: dict[str, dict[str, int]] = {
    "bulk_delivery": {"wheat": 5},
    "raider_suppress": {"wheat": 10, "meat": 5},
    "road_restore": {"ore": 3},
    "escort": {"meat": 3},
}


def build_intents(snapshot: WorldSnapshot) -> list[QuestIntent]:
    """WorldSnapshot에서 QuestIntent 목록을 생성한다."""
    world = snapshot._world  # type: ignore[attr-defined]
    intents: list[QuestIntent] = []

    # 1. needs 기반 intent
    intents.extend(_needs_intents(world))

    # 2. RoadCollapse 이벤트 기반 intent
    intents.extend(_road_intents(world))

    return intents


def _needs_intents(world: World) -> list[QuestIntent]:
    from agent_society.events.types import RoadCollapse

    # need_type → (urgency 합계, supporter id 목록)
    buckets: dict[tuple[str, str], tuple[float, list[str]]] = {}

    for agent in world.agents.values():
        if agent.role == Role.RAIDER:
            continue
        for need_type, value in agent.needs.items():
            if value < URGENCY_THRESHOLD:
                continue
            quest_type = _NEED_TO_QUEST.get(need_type)
            target = _NEED_TO_TARGET.get(need_type)
            if quest_type is None or target is None:
                continue
            key = (quest_type, target)
            prev_urgency, supporters = buckets.get(key, (0.0, []))
            buckets[key] = (max(prev_urgency, value), supporters + [agent.id])

    intents = []
    for (quest_type, target), (urgency, supporters) in buckets.items():
        if len(supporters) < 1:
            continue
        intents.append(_make_intent(
            quest_type=quest_type,
            target=target,
            urgency=urgency,
            supporters=supporters,
            issued_tick=world.tick,
        ))
    return intents


def _road_intents(world: World) -> list[QuestIntent]:
    from agent_society.events.types import RoadCollapse

    intents = []
    for event in world.active_events:
        if not isinstance(event, RoadCollapse):
            continue
        edge_key = f"{event.edge_u}→{event.edge_v}"
        # 영향 받는 agent: 양 끝 node에 있는 agent
        affected = [
            a.id for a in world.agents.values()
            if a.current_node in (event.edge_u, event.edge_v)
            and a.role != Role.RAIDER
        ]
        urgency = min(0.5 + 0.1 * len(affected), 1.0)
        intents.append(_make_intent(
            quest_type="road_restore",
            target=edge_key,
            urgency=urgency,
            supporters=affected[:5],
            issued_tick=world.tick,
        ))
    return intents


def _make_intent(
    quest_type: str,
    target: str,
    urgency: float,
    supporters: list[str],
    issued_tick: int,
) -> QuestIntent:
    base_reward = dict(_BASE_REWARD.get(quest_type, {}))
    # urgency 비례 보상 스케일
    for good in base_reward:
        base_reward[good] = max(1, int(base_reward[good] * (1 + urgency)))

    return QuestIntent(
        id=str(uuid.uuid4())[:8],
        quest_type=quest_type,
        target=target,
        urgency=round(urgency, 3),
        supporters=supporters,
        reward=base_reward,
        quest_text="",           # generator가 LLM 호출 후 채움
        status="pending",
        issued_tick=issued_tick,
        deadline_tick=issued_tick + QUEST_REFRESH_INTERVAL,
    )
