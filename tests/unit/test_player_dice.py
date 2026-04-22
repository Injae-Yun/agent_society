"""Player quest completion + FIGHT integration tests with d20 checks.

Uses deterministic FakeRng where needed to hit specific outcomes.
"""

from __future__ import annotations

from random import Random

from agent_society.agents.player import tick_player
from agent_society.events.bus import WorldEventBus
from agent_society.game.dice import CheckOutcome, d20_check
from agent_society.llm.mock_backend import MockNarrator
from agent_society.player import PlayerAction, PlayerActionType
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
from agent_society.world.snapshot import WorldSnapshot
from agent_society.world.world import build_indices


class _RollQueue:
    """Rng shim that returns rolls from a fixed queue; delegates `uniform`
    etc. to an inner Random so non-d20 callers still work."""

    def __init__(self, rolls: list[int], seed: int = 0) -> None:
        self._rolls = list(rolls)
        self._inner = Random(seed)

    def randint(self, a: int, b: int) -> int:
        if self._rolls:
            return self._rolls.pop(0)
        return self._inner.randint(a, b)

    def __getattr__(self, name):  # delegate anything else
        return getattr(self._inner, name)


def _world_and_player():
    nodes = {
        "city": Node("city", "City", RegionType.CITY, affordances=["trade"], gold=100),
        "raider.hideout": Node("raider.hideout", "HO", RegionType.RAIDER_BASE),
    }
    sword = Item("sword", Tier.BASIC, durability=50.0, max_durability=50.0)
    player = PlayerAgent(
        id="player_1", name="Hero", role=Role.PLAYER,
        home_node="city", current_node="city",
        gold=100, skill=70, combat_power=40, equipped_weapon=sword,
    )
    raider = RaiderFaction(
        id="raiders", name="R", role=Role.RAIDER,
        home_node="raider.hideout", current_node="raider.hideout",
        strength=30.0,
    )
    world = World(nodes=nodes, edges=[Edge("city", "raider.hideout", 5)],
                  agents={"player_1": player, "raiders": raider})
    build_indices(world)
    return world, player


def _with_pending(player, action_type, **kwargs):
    player.pending_action = PlayerAction(action_type, **kwargs)


def test_complete_quest_critical_success_boosts_reward():
    world, player = _world_and_player()
    gen = QuestGenerator(MockNarrator())
    gen.active_quests.append(QuestIntent(
        id="q1", quest_type="raider_suppress", target="raider",
        urgency=0.8, supporters=[], reward={"wheat": 10, "meat": 5},
        quest_text="", status="active", issued_tick=0, deadline_tick=200,
    ))
    player.active_quest_id = "q1"
    player.quest_progress = 1.0
    _with_pending(player, PlayerActionType.COMPLETE_QUEST)

    rng = _RollQueue([20])   # guaranteed critical_success
    action = tick_player(
        player, world, WorldEventBus(), gen, None, WorldSnapshot(world), rng,
    )
    assert action.action_type == "quest_complete"
    # crit success mult = 1.5; base = (10*1 + 5*1) * 4.0 = 60; × 1.5 ≈ 90
    assert action.reward_gold >= 80
    assert action.effect.get("check") == "critical_success"
    assert "story" in action.effect


def test_complete_quest_critical_failure_zero_reward():
    world, player = _world_and_player()
    gen = QuestGenerator(MockNarrator())
    gen.active_quests.append(QuestIntent(
        id="q2", quest_type="bulk_delivery", target="wheat",
        urgency=0.5, supporters=[], reward={"wheat": 5},
        quest_text="", status="active", issued_tick=0, deadline_tick=200,
    ))
    player.active_quest_id = "q2"
    player.quest_progress = 1.0
    _with_pending(player, PlayerActionType.COMPLETE_QUEST)

    rng = _RollQueue([1])    # critical_failure
    action = tick_player(
        player, world, WorldEventBus(), gen, None, WorldSnapshot(world), rng,
    )
    assert action.action_type == "quest_complete"
    assert action.reward_gold == 0
    assert action.effect.get("check") == "critical_failure"


def test_fight_critical_success_damages_raider():
    world, player = _world_and_player()
    player.current_node = "raider.hideout"
    build_indices(world)
    gen = QuestGenerator(MockNarrator())
    _with_pending(player, PlayerActionType.FIGHT)

    before = world.agents["raiders"].strength
    rng = _RollQueue([20])   # critical hit
    action = tick_player(
        player, world, WorldEventBus(), gen, None, WorldSnapshot(world), rng,
    )
    assert action.action_type == "fight"
    assert world.agents["raiders"].strength < before
    assert action.result == "critical_success"
