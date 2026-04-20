"""QuestContext — 월드 단면 스냅샷. LLM 입력의 맥락 데이터 구조.

LLM이 '왜 이 퀘스트인가'를 이해하려면 intent만으론 부족하다.
여러 agent의 needs 상태, 활성 이벤트, 재화 scarcity를 한꺼번에 전달해야
설득력 있는 서사가 나온다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_society.config.parameters import URGENCY_THRESHOLD
from agent_society.schema import NeedType, World
from agent_society.simulation.clock import format_time, tick_to_season
from agent_society.world import world as world_ops


@dataclass
class UrgentAgentInfo:
    agent_id: str
    name: str
    role: str
    need_type: NeedType
    urgency: float       # 0.0 ~ 1.0
    location: str        # current_node id


@dataclass
class QuestContext:
    tick: int
    season: str
    # 임계 초과 needs — LLM이 긴급도·동기를 판단
    urgent_agents: list[UrgentAgentInfo] = field(default_factory=list)
    # 활성 WorldEvent 요약 (흉년·도로 붕괴 등 — 퀘스트 발생 원인)
    active_event_summaries: list[str] = field(default_factory=list)
    # 주요 재화 scarcity (0 = 풍부, 1 = 심각한 부족)
    scarcity_map: dict[str, float] = field(default_factory=dict)
    # 의뢰 supporter 페르소나 (프롬프트에 직접 삽입)
    supporter_personas: list[str] = field(default_factory=list)


# 추적할 주요 재화 목록
_TRACKED_GOODS = ("wheat", "meat", "fruit", "cooked_meal", "ore", "sword", "plow")


def build_context(world: World, supporter_ids: list[str] | None = None) -> QuestContext:
    """월드 스냅샷에서 QuestContext를 조립한다."""
    urgent: list[UrgentAgentInfo] = []

    for agent in sorted(world.agents.values(), key=lambda a: a.id):
        for need_type, value in agent.needs.items():
            if value >= URGENCY_THRESHOLD:
                urgent.append(UrgentAgentInfo(
                    agent_id=agent.id,
                    name=agent.name,
                    role=agent.role.value,
                    need_type=need_type,
                    urgency=round(value, 3),
                    location=agent.current_node,
                ))

    # 활성 이벤트 요약
    event_summaries = [
        f"{type(e).__name__}(tick={e.tick}, source={e.source})"
        for e in world.active_events
    ]

    # 재화 scarcity
    scarcity_map = {
        good: round(world_ops.scarcity(world, good), 4)
        for good in _TRACKED_GOODS
    }

    # Supporter 페르소나
    personas: list[str] = []
    for sid in (supporter_ids or []):
        agent = world.agents.get(sid)
        if agent:
            personas.append(f"{agent.name} ({agent.role.value}, {agent.current_node})")

    return QuestContext(
        tick=world.tick,
        season=tick_to_season(world.tick),
        urgent_agents=urgent,
        active_event_summaries=event_summaries,
        scarcity_map=scarcity_map,
        supporter_personas=personas,
    )
