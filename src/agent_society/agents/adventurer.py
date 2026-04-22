"""AdventurerAgent tick — pick & complete pending quests so the world heals.

Design notes:
  * Common-tier quests are fair game; heroic-tier is reserved for the player.
  * One quest per adventurer at a time; `quest_progress` ticks up by
    `skill / 50 / QUEST_WORK_TICKS` per tick, so a median adventurer finishes
    in ~48 ticks (two in-game days).
  * Completion fires `apply_completion()` (world-state mutation) *and* pays
    the taker in gold converted from the reward goods.
  * State changes (quest_gen accept/complete, reward, world effects) happen
    here — the returned action object is just a recorder record.
"""

from __future__ import annotations

import logging
from random import Random

from agent_society.agents.actions import (
    ConsumeFoodAction,
    NoAction,
    QuestAcceptAction,
    QuestCompleteAction,
    QuestProgressAction,
    TravelAction,
)
from agent_society.economy.config import BASE_VALUE
from agent_society.events.bus import WorldEventBus
from agent_society.events.types import EventSeverity, QuestAccepted, QuestResolved
from agent_society.quests.effects import apply_completion
from agent_society.schema import AdventurerAgent, NeedType, QuestIntent, World
from agent_society.world.snapshot import WorldSnapshot

log = logging.getLogger(__name__)

CITY_NODE = "city"

# How long a "standard" quest takes a median-skill adventurer.
QUEST_WORK_TICKS = 32
_SKILL_BASE = 50.0

# Gold equivalent paid per unit of each reward good on completion.
# Reward needs to cover ~QUEST_WORK_TICKS × meal_cost, otherwise adventurers
# lose money doing quests and starve out of the system.
_REWARD_GOLD_MULT = 4.0


def tick_adventurer(
    agent: AdventurerAgent,
    world: World,
    bus: WorldEventBus,
    quest_gen,
    snapshot: WorldSnapshot,
    rng: Random,
) -> object:
    """Main entry: returns an action record and performs side-effects in place."""

    # 1. Eat when hungry — adventurers use the same consume path as others.
    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    if hunger > 0.5:
        eat = _eat_if_possible(agent, snapshot)
        if eat is not None:
            return eat

    # 2. Active quest → advance it
    if agent.active_quest_id is not None:
        quest = _find_quest(quest_gen, agent.active_quest_id)
        if quest is None or quest.status != "active":
            # Cancelled or expired out from under us — reset
            agent.active_quest_id = None
            agent.quest_progress = 0.0
        else:
            agent.quest_progress += (max(agent.skill, 1.0) / _SKILL_BASE) / QUEST_WORK_TICKS
            if agent.quest_progress >= 1.0:
                return _complete_quest(agent, quest, world, bus, quest_gen)
            return QuestProgressAction(
                agent=agent, quest_id=quest.id, progress=agent.quest_progress,
            )

    # 3. Idle → look for a new quest (any pending, common tier, unclaimed)
    candidate = _pick_best_quest(quest_gen)
    if candidate is not None:
        return _accept_quest(agent, candidate, world, bus, quest_gen)

    # 4. Nothing to do — head back to the city if strayed
    if agent.current_node != CITY_NODE:
        return TravelAction(agent=agent, target_node=CITY_NODE)
    return NoAction(agent=agent)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _eat_if_possible(agent, snapshot: WorldSnapshot):
    """Reuse the producer-style food picker to avoid divergent eating logic."""
    from agent_society.agents.selection import _food_at_node
    meal = _food_at_node(agent, snapshot)
    if meal is None:
        return None
    food, qty = meal
    return ConsumeFoodAction(
        agent=agent, food_good=food, node_id=agent.current_node, qty=qty,
    )


def _find_quest(quest_gen, quest_id: str) -> QuestIntent | None:
    for q in getattr(quest_gen, "active_quests", []):
        if q.id == quest_id:
            return q
    return None


def _pick_best_quest(quest_gen) -> QuestIntent | None:
    """Highest (urgency × reward-value) unclaimed common-tier quest."""
    pending = getattr(quest_gen, "pending_quests", lambda: [])()
    candidates = [
        q for q in pending
        if q.taker_id is None and q.tier != "heroic"
    ]
    if not candidates:
        return None

    def score(q: QuestIntent) -> float:
        reward_value = sum(qty * BASE_VALUE.get(g, 1.0) for g, qty in q.reward.items())
        return q.urgency * max(reward_value, 1.0)

    return max(candidates, key=score)


def _accept_quest(
    agent: AdventurerAgent,
    quest: QuestIntent,
    world: World,
    bus: WorldEventBus,
    quest_gen,
) -> QuestAcceptAction:
    quest_gen.accept(quest.id)
    quest.taker_id = agent.id
    agent.active_quest_id = quest.id
    agent.quest_progress = 0.0

    bus.publish(QuestAccepted(
        tick=world.tick, source="adventurer", severity=EventSeverity.INFO,
        quest_id=quest.id, acceptor=agent.id,
    ))
    log.info("[%s] accepted quest %s (%s → %s)",
             agent.id, quest.id, quest.quest_type, quest.target)
    return QuestAcceptAction(
        agent=agent, quest_id=quest.id,
        quest_type=quest.quest_type, target=quest.target,
    )


def _complete_quest(
    agent: AdventurerAgent,
    quest: QuestIntent,
    world: World,
    bus: WorldEventBus,
    quest_gen,
) -> QuestCompleteAction:
    # Mark status
    quest_gen.complete(quest.id)

    # Apply world effects
    effect = apply_completion(quest, world)

    # Convert reward goods into gold and pay the adventurer
    reward_gold = max(1, int(sum(
        qty * BASE_VALUE.get(good, 1.0) for good, qty in quest.reward.items()
    ) * _REWARD_GOLD_MULT))
    agent.gold += reward_gold

    # Reset agent state
    agent.active_quest_id = None
    agent.quest_progress = 0.0

    bus.publish(QuestResolved(
        tick=world.tick, source="adventurer", severity=EventSeverity.INFO,
        quest_id=quest.id, success=True,
    ))
    log.info("[%s] completed quest %s → %s (+%dg)",
             agent.id, quest.id, effect, reward_gold)
    return QuestCompleteAction(
        agent=agent, quest_id=quest.id, quest_type=quest.quest_type,
        reward_gold=reward_gold, effect=effect,
    )
