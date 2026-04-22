"""PlayerAgent dispatch tests.

Uses ScriptedPlayer to queue deterministic actions and verifies that each
PlayerActionType lands the right world-state change.
"""

from __future__ import annotations

from random import Random

import pytest

from agent_society.agents.society import AgentSociety
from agent_society.events.bus import WorldEventBus
from agent_society.llm.mock_backend import MockNarrator
from agent_society.player import PlayerAction, PlayerActionType, ScriptedPlayer
from agent_society.quests import QuestGenerator
from agent_society.schema import (
    Agent,
    Edge,
    Item,
    NeedType,
    Node,
    PlayerAgent,
    QuestIntent,
    RaiderFaction,
    RegionType,
    Role,
    Tier,
    World,
)
from agent_society.world.world import build_indices


def _world_with_player() -> tuple[World, PlayerAgent]:
    nodes = {
        "city": Node("city", "City", RegionType.CITY,
                     stockpile={"wheat": 40, "meat": 20, "sword": 2, "cooked_meal": 5},
                     affordances=["trade", "cook"], gold=200),
        "farm": Node("farm", "Farmland", RegionType.FARMLAND,
                     stockpile={"wheat": 30, "meat": 20}, affordances=["trade"], gold=200),
        "raider.hideout": Node("raider.hideout", "Hideout", RegionType.RAIDER_BASE),
    }
    edges = [Edge("city", "farm", travel_cost=3, base_threat=0.1)]
    sword = Item("sword", Tier.BASIC, durability=50.0, max_durability=50.0)
    player = PlayerAgent(
        id="player_1", name="Hero", role=Role.PLAYER,
        home_node="city", current_node="city",
        gold=100, skill=70, combat_power=35, equipped_weapon=sword,
    )
    raider = RaiderFaction(
        id="raiders", name="R", role=Role.RAIDER,
        home_node="raider.hideout", current_node="raider.hideout", strength=50.0,
    )
    farmer = Agent(id="farmer_1", name="F", role=Role.FARMER,
                   home_node="farm", current_node="farm",
                   needs={NeedType.SAFETY: 0.95})
    agents = {"player_1": player, "raiders": raider, "farmer_1": farmer}
    world = World(nodes=nodes, edges=edges, agents=agents)
    build_indices(world)
    return world, player


def _run(world, player, actions):
    iface = ScriptedPlayer(actions)
    bus = WorldEventBus()
    gen = QuestGenerator(MockNarrator())
    # Deterministic rng — fights, event rolls etc. all reproducible.
    society = AgentSociety(bus=bus, rng=Random(42), quest_gen=gen, player_interface=iface)
    for _ in range(len(actions) + 1):
        society.tick(world)
    return gen


def test_player_move_travels_to_node():
    world, player = _world_with_player()
    _run(world, player, [PlayerAction(PlayerActionType.MOVE, target_node="farm")])
    # move is a TravelAction → moves immediately, but sets travel_ticks_remaining
    assert player.current_node == "farm"


def test_player_buy_deducts_gold_and_adds_inventory():
    world, player = _world_with_player()
    gold_before = player.gold
    _run(world, player, [PlayerAction(PlayerActionType.BUY, good="wheat", qty=3)])
    assert player.inventory.get("wheat", 0) >= 1
    assert player.gold < gold_before


def test_player_sell_adds_gold():
    world, player = _world_with_player()
    player.inventory["wheat"] = 5
    gold_before = player.gold
    _run(world, player, [PlayerAction(PlayerActionType.SELL, good="wheat", qty=3)])
    assert player.gold >= gold_before
    assert player.inventory.get("wheat", 0) < 5


def test_player_fight_hits_colocated_raider():
    world, player = _world_with_player()
    # Move player to raider hideout manually
    world.agents["player_1"].current_node = "raider.hideout"
    build_indices(world)
    str_before = world.agents["raiders"].strength
    _run(world, player, [PlayerAction(PlayerActionType.FIGHT)])
    # Outcome is random — but something should change (damage dealt or gold lost)
    str_after = world.agents["raiders"].strength
    changed = str_after < str_before or player.gold != 100
    assert changed, "Fight had no effect"


def test_player_accept_and_complete_quest():
    world, player = _world_with_player()
    bus = WorldEventBus()
    gen = QuestGenerator(MockNarrator())
    quest = QuestIntent(
        id="q1", quest_type="raider_suppress", target="raider",
        urgency=0.95, supporters=["farmer_1"], reward={"wheat": 10, "meat": 5},
        quest_text="", status="pending", issued_tick=0, deadline_tick=200,
        tier="heroic",       # player-eligible
    )
    gen.active_quests.append(quest)

    iface = ScriptedPlayer([
        PlayerAction(PlayerActionType.ACCEPT_QUEST, quest_id="q1"),
    ] + [PlayerAction(PlayerActionType.WORK_QUEST)] * 40 +  # enough to finish
        [PlayerAction(PlayerActionType.COMPLETE_QUEST)])

    society = AgentSociety(bus=bus, rng=Random(42), quest_gen=gen, player_interface=iface)
    for _ in range(45):
        society.tick(world)

    assert player.active_quest_id is None
    assert "q1" in player.quest_log
    assert quest.status == "completed"
    # Effect: raider strength dropped
    assert world.agents["raiders"].strength < 50.0


def test_heroic_quest_skipped_by_adventurer():
    """Adventurer should not pick heroic quests."""
    from agent_society.agents.adventurer import _pick_best_quest
    gen = QuestGenerator(MockNarrator())
    gen.active_quests.append(QuestIntent(
        id="qh", quest_type="raider_suppress", target="raider",
        urgency=0.95, supporters=[], reward={"wheat": 10},
        quest_text="", status="pending", issued_tick=0, deadline_tick=200,
        tier="heroic",
    ))
    assert _pick_best_quest(gen) is None
