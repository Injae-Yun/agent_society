"""Unit tests for quest intent generation and merging."""

from __future__ import annotations

import pytest

from agent_society.llm.mock_backend import MockNarrator
from agent_society.quests import QuestGenerator, build_intents, merge_intents
from agent_society.quests.intent import _make_intent
from agent_society.schema import NeedType, QuestIntent
from agent_society.world.builder import build_mvp_world
from agent_society.world.snapshot import WorldSnapshot


@pytest.fixture
def world_with_high_needs():
    world = build_mvp_world()
    for agent in world.agents.values():
        agent.needs[NeedType.HUNGER] = 0.85
        agent.needs[NeedType.SAFETY] = 0.80
    return world


def test_build_intents_returns_intents_when_needs_high(world_with_high_needs):
    snap = WorldSnapshot(world_with_high_needs)
    intents = build_intents(snap)
    assert len(intents) >= 1
    types = {i.quest_type for i in intents}
    assert "bulk_delivery" in types
    assert "raider_suppress" in types


def test_build_intents_empty_when_needs_low():
    world = build_mvp_world()
    # all needs at 0
    for agent in world.agents.values():
        for nt in NeedType:
            agent.needs[nt] = 0.0
    snap = WorldSnapshot(world)
    intents = build_intents(snap)
    assert intents == []


def test_merge_deduplicates_same_type_target():
    a = _make_intent("bulk_delivery", "wheat", 0.8, ["a1", "a2"], issued_tick=0)
    b = _make_intent("bulk_delivery", "wheat", 0.7, ["a3"], issued_tick=0)
    merged = merge_intents([a, b])
    assert len(merged) == 1
    assert set(merged[0].supporters) == {"a1", "a2", "a3"}
    assert merged[0].urgency == pytest.approx(0.8)


def test_merge_keeps_different_targets_separate():
    a = _make_intent("bulk_delivery", "wheat", 0.8, ["a1"], issued_tick=0)
    b = _make_intent("bulk_delivery", "ore", 0.7, ["a2"], issued_tick=0)
    merged = merge_intents([a, b])
    assert len(merged) == 2


def test_merge_is_idempotent():
    a = _make_intent("raider_suppress", "raider", 0.9, ["a1"], issued_tick=0)
    once = merge_intents([a])
    twice = merge_intents(once)
    assert len(once) == len(twice) == 1


def test_quest_generator_with_mock(world_with_high_needs):
    gen = QuestGenerator(MockNarrator())
    gen.tick(WorldSnapshot(world_with_high_needs))
    assert len(gen.active_quests) >= 1
    for q in gen.active_quests:
        assert q.status == "pending"
        assert q.quest_text != ""
        assert q.deadline_tick > world_with_high_needs.tick


def test_quest_generator_accept_and_complete(world_with_high_needs):
    gen = QuestGenerator(MockNarrator())
    gen.tick(WorldSnapshot(world_with_high_needs))
    quest = gen.pending_quests()[0]

    assert gen.accept(quest.id)
    assert quest.status == "active"

    completed = gen.complete(quest.id)
    assert completed is not None
    assert completed.status == "completed"


def test_quest_generator_expire_on_refresh(world_with_high_needs):
    gen = QuestGenerator(MockNarrator())
    gen.tick(WorldSnapshot(world_with_high_needs))
    assert len(gen.pending_quests()) >= 1

    # 두 번째 갱신 — 수락 안 한 pending 퀘스트는 사라짐
    gen.tick(WorldSnapshot(world_with_high_needs))
    # 각 갱신마다 이전 pending은 제거되고 새 퀘스트로 교체
    for q in gen.active_quests:
        assert q.issued_tick == world_with_high_needs.tick
