"""MockNarrator — deterministic stub for tests and LLM fallback.

Templates chosen so unit tests can assert on the outcome label.
"""

from __future__ import annotations

from agent_society.llm.base import QuestResolution


_OUTCOME_PREFIX = {
    "critical_success": "🏅 대성공",
    "success":          "✨ 성공",
    "partial":          "🪨 진행",
    "failure":          "💢 실패",
    "critical_failure": "☠ 대실패",
}

_TYPE_KR = {
    "bulk_delivery":   "물자 납품",
    "raider_suppress": "도적 토벌",
    "road_restore":    "도로 복구",
    "escort":          "호위",
}


class MockNarrator:
    """Returns deterministic strings — no LLM call."""

    def narrate(self, intent: object, context: object) -> str:
        quest_type = getattr(intent, "quest_type", "unknown")
        target = getattr(intent, "target", "?")
        return f"[MOCK] {quest_type} @ {target}"

    def narrate_resolution(self, resolution: QuestResolution) -> str:
        prefix = _OUTCOME_PREFIX.get(resolution.outcome, resolution.outcome)
        quest_kr = _TYPE_KR.get(resolution.quest_type, resolution.quest_type)
        return (
            f"{prefix} — {resolution.actor_name}가 {quest_kr}({resolution.target}) "
            f"판정에서 1d20+{resolution.modifier:+d}={resolution.total} vs DC {resolution.dc}. "
            f"보상 +{resolution.reward_gold}g."
        )
