"""유사한 QuestIntent 병합 — 같은 quest_type + target이면 supporter 통합."""

from __future__ import annotations

from agent_society.schema import QuestIntent


def merge_intents(intents: list[QuestIntent]) -> list[QuestIntent]:
    """(quest_type, target)이 동일한 intent를 하나로 병합한다."""
    buckets: dict[tuple[str, str], list[QuestIntent]] = {}
    for intent in intents:
        key = (intent.quest_type, intent.target)
        buckets.setdefault(key, []).append(intent)

    merged = []
    for group in buckets.values():
        if len(group) == 1:
            merged.append(group[0])
        else:
            merged.append(_merge_group(group))
    return merged


def _merge_group(group: list[QuestIntent]) -> QuestIntent:
    base = group[0]
    all_supporters: list[str] = []
    seen: set[str] = set()
    for intent in group:
        for sid in intent.supporters:
            if sid not in seen:
                all_supporters.append(sid)
                seen.add(sid)

    max_urgency = max(i.urgency for i in group)
    merged_reward: dict[str, int] = {}
    for intent in group:
        for good, qty in intent.reward.items():
            merged_reward[good] = max(merged_reward.get(good, 0), qty)

    return QuestIntent(
        id=base.id,
        quest_type=base.quest_type,
        target=base.target,
        urgency=round(max_urgency, 3),
        supporters=all_supporters,
        reward=merged_reward,
        quest_text="",
        status="pending",
        issued_tick=base.issued_tick,
        deadline_tick=base.deadline_tick,
    )
