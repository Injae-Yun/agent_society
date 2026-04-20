"""QuestGenerator — 7일(1008 tick)마다 퀘스트를 갱신한다."""

from __future__ import annotations

import logging

from agent_society.llm.base import QuestNarrator
from agent_society.quests.context import build_context
from agent_society.quests.intent import build_intents
from agent_society.quests.merger import merge_intents
from agent_society.schema import QuestIntent
from agent_society.world.snapshot import WorldSnapshot

log = logging.getLogger(__name__)


class QuestGenerator:
    def __init__(self, narrator: QuestNarrator) -> None:
        self._narrator = narrator
        self.active_quests: list[QuestIntent] = []

    def tick(self, snapshot: WorldSnapshot) -> None:
        """퀘스트 갱신: 기존 만료 → 신규 생성 → LLM 서사화."""
        world = snapshot._world  # type: ignore[attr-defined]

        # 1. 만료 처리
        self.active_quests = [
            q for q in self.active_quests
            if q.status == "active"           # 수락된 퀘스트는 유지
        ]

        # 2. 신규 intent 생성 + 병합
        raw = build_intents(snapshot)
        merged = merge_intents(raw)
        log.info("QuestGenerator: %d raw → %d merged intents", len(raw), len(merged))

        # 3. LLM 서사화
        context = build_context(world)
        narrated: list[QuestIntent] = []
        for intent in merged:
            text = self._narrator.narrate(intent, context)
            intent.quest_text = text
            narrated.append(intent)
            log.debug("Quest [%s] %s: %s", intent.id, intent.quest_type, text[:60])

        self.active_quests.extend(narrated)
        log.info(
            "QuestGenerator: %d quests active (tick=%d)",
            len(self.active_quests), world.tick,
        )

    def pending_quests(self) -> list[QuestIntent]:
        return [q for q in self.active_quests if q.status == "pending"]

    def accept(self, quest_id: str) -> bool:
        for q in self.active_quests:
            if q.id == quest_id and q.status == "pending":
                q.status = "active"
                return True
        return False

    def complete(self, quest_id: str) -> QuestIntent | None:
        for q in self.active_quests:
            if q.id == quest_id and q.status == "active":
                q.status = "completed"
                return q
        return None
