"""Adventurer + quest effect tests."""

from __future__ import annotations

from random import Random

import pytest

from agent_society.agents.adventurer import tick_adventurer
from agent_society.agents.society import AgentSociety
from agent_society.events.bus import WorldEventBus
from agent_society.llm.mock_backend import MockNarrator
from agent_society.quests import QuestGenerator
from agent_society.quests.effects import apply_completion
from agent_society.schema import (
    AdventurerAgent,
    Agent,
    Edge,
    NeedType,
    Node,
    QuestIntent,
    RaiderFaction,
    RegionType,
    Role,
    World,
)
from agent_society.world.snapshot import WorldSnapshot
from agent_society.world.world import build_indices


def _world_with_advs() -> tuple[World, QuestGenerator]:
    nodes = {
        "city": Node("city", "City", RegionType.CITY,
                     stockpile={"wheat": 50, "meat": 20, "cooked_meal": 10},
                     affordances=["trade", "cook"]),
        "farm": Node("farm", "Farmland", RegionType.FARMLAND,
                     stockpile={"wheat": 30}, affordances=["trade"]),
        "raider.hideout": Node("raider.hideout", "Hideout", RegionType.RAIDER_BASE),
    }
    edges = [Edge("city", "farm", travel_cost=5, base_threat=0.1)]
    agents = {
        "adv_1": AdventurerAgent(
            "adv_1", "Ryn", Role.ADVENTURER, "city", "city",
            gold=50, skill=60,
        ),
        "raiders": RaiderFaction(
            "raiders", "Raiders", Role.RAIDER,
            "raider.hideout", "raider.hideout", strength=80.0,
        ),
        "farmer_1": Agent("farmer_1", "F1", Role.FARMER, "farm", "farm",
                          needs={NeedType.SAFETY: 0.9}),
    }
    world = World(nodes=nodes, edges=edges, agents=agents)
    build_indices(world)

    gen = QuestGenerator(MockNarrator())
    # Seed one pending quest directly (bypass 7-day cycle for unit testing)
    gen.active_quests.append(QuestIntent(
        id="q1", quest_type="raider_suppress", target="raider",
        urgency=0.9, supporters=["farmer_1"], reward={"wheat": 10, "meat": 5},
        quest_text="test", status="pending",
        issued_tick=0, deadline_tick=200,
    ))
    return world, gen


def test_adventurer_accepts_pending_quest():
    world, gen = _world_with_advs()
    adv = world.agents["adv_1"]
    action = tick_adventurer(adv, world, WorldEventBus(), gen, WorldSnapshot(world), Random(1))
    assert action.action_type == "quest_accept"
    assert adv.active_quest_id == "q1"
    assert gen.active_quests[0].status == "active"
    assert gen.active_quests[0].taker_id == "adv_1"


def test_adventurer_progresses_then_completes():
    world, gen = _world_with_advs()
    adv = world.agents["adv_1"]
    bus = WorldEventBus()
    rng = Random(1)
    snap = WorldSnapshot(world)

    # Accept
    tick_adventurer(adv, world, bus, gen, snap, rng)
    # Force progress near completion — one more tick's increment pushes ≥1.0
    adv.quest_progress = 0.99
    raider_before = world.agents["raiders"].strength
    farmer_safety_before = world.agents["farmer_1"].needs[NeedType.SAFETY]

    action = tick_adventurer(adv, world, bus, gen, snap, rng)
    assert action.action_type == "quest_complete"
    # Effect: raider strength dropped
    assert world.agents["raiders"].strength < raider_before
    # Effect: farmer safety relieved
    assert world.agents["farmer_1"].needs[NeedType.SAFETY] < farmer_safety_before
    # Adventurer paid reward
    assert adv.gold > 50
    assert adv.active_quest_id is None
    assert adv.quest_progress == 0.0


def test_apply_completion_bulk_delivery():
    world, _ = _world_with_advs()
    q = QuestIntent(
        id="q2", quest_type="bulk_delivery", target="ore",
        urgency=0.8, supporters=[], reward={"ore": 5},
        quest_text="", status="active", issued_tick=0, deadline_tick=100,
    )
    before = world.nodes["city"].stockpile.get("ore", 0)
    effect = apply_completion(q, world)
    assert effect["effect"] == "bulk_delivery"
    assert world.nodes["city"].stockpile.get("ore", 0) > before


def test_apply_completion_road_restore():
    world, _ = _world_with_advs()
    world.edges[0].severed = True
    q = QuestIntent(
        id="q3", quest_type="road_restore", target="city→farm",
        urgency=0.7, supporters=[], reward={"ore": 3},
        quest_text="", status="active", issued_tick=0, deadline_tick=100,
    )
    effect = apply_completion(q, world)
    assert effect["effect"] == "road_restore"
    assert world.edges[0].severed is False


def test_adventurer_society_integration():
    """End-to-end: AgentSociety dispatches AdventurerAgent to the quest tick."""
    world, gen = _world_with_advs()
    bus = WorldEventBus()
    society = AgentSociety(bus=bus, quest_gen=gen)

    # Tick a few times — adventurer should accept + work
    for _ in range(5):
        society.tick(world)

    adv = world.agents["adv_1"]
    assert adv.active_quest_id == "q1"
    assert 0.0 < adv.quest_progress <= 1.0
