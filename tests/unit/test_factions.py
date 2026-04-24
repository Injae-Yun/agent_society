"""Faction + reputation tests (M6)."""

from __future__ import annotations

from random import Random

import pytest

from agent_society.factions import (
    DEFAULT_FACTIONS,
    apply_quest_completion_reputation,
    propagate_rumors,
    reputation_tier,
    role_to_faction,
)
from agent_society.schema import (
    Agent,
    NeedType,
    Node,
    PlayerAgent,
    QuestIntent,
    RegionType,
    Role,
    World,
)
from agent_society.world.world import build_indices


def _world() -> tuple[World, PlayerAgent]:
    nodes = {"city": Node("city", "C", RegionType.CITY),
             "farm": Node("farm", "F", RegionType.FARMLAND)}
    player = PlayerAgent(
        id="player_1", name="Hero", role=Role.PLAYER,
        home_node="city", current_node="city",
        gold=100, faction_id="civic",
    )
    cook = Agent(id="cook_1", name="C", role=Role.COOK,
                 home_node="city", current_node="city", faction_id="civic")
    farmer = Agent(id="farmer_1", name="F", role=Role.FARMER,
                   home_node="farm", current_node="farm", faction_id="rural")
    neighbour = Agent(id="cook_2", name="C2", role=Role.COOK,
                      home_node="city", current_node="city", faction_id="civic")
    world = World(nodes=nodes, edges=[],
                  agents={"player_1": player, "cook_1": cook,
                          "farmer_1": farmer, "cook_2": neighbour})
    build_indices(world)
    return world, player


def test_role_to_faction_defaults():
    assert role_to_faction(Role.FARMER) == "rural"
    assert role_to_faction(Role.COOK) == "civic"
    assert role_to_faction(Role.RAIDER) == "raiders"


def test_reputation_tier_boundaries():
    assert reputation_tier(80) == "hero"
    assert reputation_tier(40) == "friend"
    assert reputation_tier(0) == "neutral"
    assert reputation_tier(-50) == "wary"
    assert reputation_tier(-80) == "enemy"


def test_quest_completion_updates_player_and_supporter():
    world, player = _world()
    quest = QuestIntent(
        id="q1", quest_type="bulk_delivery", target="wheat",
        urgency=0.8, supporters=["cook_1", "farmer_1"],
        reward={"wheat": 5}, quest_text="", status="active",
        issued_tick=0, deadline_tick=200,
    )
    deltas = apply_quest_completion_reputation(world, quest, player, outcome_mult=1.0)
    # civic (cook_1) + rural (farmer_1) each gain reputation
    assert "civic" in deltas
    assert "rural" in deltas
    # Player's canonical rep updated
    assert player.reputation["civic"] > 0
    assert player.reputation["rural"] > 0
    # Supporters now know the new rep first-hand
    assert world.agents["cook_1"].known_player_rep["civic"] == player.reputation["civic"]


def test_critical_failure_reduces_reputation():
    world, player = _world()
    player.reputation["civic"] = 20.0
    quest = QuestIntent(
        id="q2", quest_type="bulk_delivery", target="wheat",
        urgency=0.5, supporters=["cook_1"], reward={"wheat": 3},
        quest_text="", status="active", issued_tick=0, deadline_tick=200,
    )
    apply_quest_completion_reputation(world, quest, player, outcome_mult=0.0)
    assert player.reputation["civic"] < 20.0


def test_rumor_propagates_to_colocated_peer():
    world, player = _world()
    # cook_1 directly met the player and knows rep
    world.agents["cook_1"].known_player_rep["civic"] = 40.0
    # cook_2 at the same node starts ignorant
    assert "civic" not in world.agents["cook_2"].known_player_rep

    # High prob + fixed seed so cross-pollination is deterministic
    transfers = propagate_rumors(world, Random(1), prob=1.0)
    assert transfers > 0
    assert "civic" in world.agents["cook_2"].known_player_rep
    # Value moved toward the knower's 40, attenuated by decay
    assert 0 < world.agents["cook_2"].known_player_rep["civic"] <= 40.0


def test_rumor_does_not_jump_between_unrelated_nodes():
    world, player = _world()
    world.agents["cook_1"].known_player_rep["civic"] = 50.0
    propagate_rumors(world, Random(1), prob=1.0)
    # farmer_1 is at farm — should not receive the rumor this tick
    assert "civic" not in world.agents["farmer_1"].known_player_rep


def test_builder_assigns_factions_from_role():
    from pathlib import Path
    from agent_society.world.builder import build_world_from_yaml

    world = build_world_from_yaml(Path(__file__).parents[2] / "configs" / "mvp_scenario.yaml")
    # every agent should have a faction assigned
    for aid, agent in world.agents.items():
        assert agent.faction_id is not None, f"agent {aid} missing faction"
    # A known role → known faction
    farmers = [a for a in world.agents.values() if a.role == Role.FARMER]
    assert all(a.faction_id == "rural" for a in farmers)
    raiders = [a for a in world.agents.values() if a.role == Role.RAIDER]
    assert all(a.faction_id == "raiders" for a in raiders)
    # World carries the faction registry
    assert "civic" in world.factions
    assert world.factions["raiders"].hostile_by_default is True
