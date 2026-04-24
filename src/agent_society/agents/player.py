"""PlayerAgent tick — dispatches PlayerAction from the interface.

Shares quest machinery with Adventurer (`quests/effects.apply_completion`) so
completed Player quests have the same world effects. Differences:
  * Input-driven: the interface supplies the action, no utility scoring.
  * Can take `heroic`-tier quests (Adventurer cannot).
  * Dedicated FIGHT action for raider combat.
"""

from __future__ import annotations

import logging
from random import Random
from typing import TYPE_CHECKING

from agent_society.agents.actions import (
    BuyAction,
    ConsumeFoodAction,
    FightAction,
    NoAction,
    QuestAcceptAction,
    QuestCompleteAction,
    QuestProgressAction,
    RestAction,
    SellAction,
    TravelAction,
)
from agent_society.economy.config import BASE_VALUE
from agent_society.economy.exchange import node_price
from agent_society.events.bus import WorldEventBus
from agent_society.events.types import EventSeverity, QuestAccepted, QuestResolved
from agent_society.factions.reputation import apply_quest_completion_reputation
from agent_society.game.dice import (
    CheckOutcome,
    CheckResult,
    d20_check,
    dc_for_urgency,
    outcome_multiplier,
    stat_modifier,
)
from agent_society.llm.base import QuestNarrator, QuestResolution
from agent_society.llm.mock_backend import MockNarrator
from agent_society.quests.effects import apply_completion
from agent_society.schema import NeedType, PlayerAgent, QuestIntent, RaiderFaction, World
from agent_society.world.snapshot import WorldSnapshot

if TYPE_CHECKING:
    from agent_society.player.interface import PlayerInterface

log = logging.getLogger(__name__)


# Same progress model as the Adventurer — a median-skill player clears a
# standard quest in about 32 WORK_QUEST ticks.
QUEST_WORK_TICKS = 32
_SKILL_BASE = 50.0
_REWARD_GOLD_MULT = 4.0


def tick_player(
    player: PlayerAgent,
    world: World,
    bus: WorldEventBus,
    quest_gen,
    interface: "PlayerInterface | None",
    snapshot: WorldSnapshot,
    rng: Random,
    narrator: QuestNarrator | None = None,
) -> object:
    """Run one Player tick. Returns a recorder action (may be NoAction)."""

    # Narrator fallback — MockNarrator is deterministic and always available.
    if narrator is None:
        narrator = MockNarrator()

    # 1. Pull input: prefer any pre-staged pending_action, else ask the interface.
    action = player.pending_action
    player.pending_action = None
    if action is None and interface is not None:
        action = interface.next_action(world, player)

    if action is None:
        return NoAction(agent=player)

    try:
        return _dispatch(action, player, world, bus, quest_gen, snapshot, rng, narrator)
    except Exception:
        log.exception("Player action dispatch failed (%s) — idling", action)
        return NoAction(agent=player)


# ── Dispatch ──────────────────────────────────────────────────────────────────

def _dispatch(pa, player, world, bus, quest_gen, snapshot, rng, narrator):
    from agent_society.player.actions import PlayerActionType as T

    if pa.type == T.MOVE:
        if not pa.target_node or pa.target_node not in world.nodes:
            return NoAction(agent=player)
        return TravelAction(agent=player, target_node=pa.target_node)

    if pa.type == T.BUY:
        return _make_buy(player, world, pa.good, pa.qty or 1)

    if pa.type == T.SELL:
        return _make_sell(player, world, pa.good, pa.qty or 1)

    if pa.type == T.CONSUME:
        # Use the shared food picker so Player obeys the same rules as NPCs.
        from agent_society.agents.selection import _food_at_node
        meal = _food_at_node(player, snapshot)
        if meal is None:
            return NoAction(agent=player)
        good, qty = meal
        return ConsumeFoodAction(
            agent=player, food_good=good, node_id=player.current_node, qty=qty,
        )

    if pa.type == T.FIGHT:
        return _fight(player, world, bus, rng)

    if pa.type == T.COMPLETE_QUEST:
        return _complete_quest(player, world, bus, quest_gen, rng, narrator)

    if pa.type == T.REST:
        # Light recovery — not a full meal, but slow safety/hunger regen.
        player.needs[NeedType.HUNGER] = max(0.0, player.needs.get(NeedType.HUNGER, 0.0) - 0.05)
        player.needs[NeedType.SAFETY] = max(0.0, player.needs.get(NeedType.SAFETY, 0.0) - 0.05)
        return RestAction(agent=player)

    if pa.type == T.ACCEPT_QUEST:
        return _accept_quest(player, pa.quest_id, world, bus, quest_gen)

    if pa.type == T.WORK_QUEST:
        return _work_quest(player, world, bus, quest_gen)

    return NoAction(agent=player)


# ── BUY / SELL helpers — reuse merchant action dataclasses ────────────────────

def _make_buy(player, world, good, qty):
    if good is None or qty <= 0:
        return NoAction(agent=player)
    node = world.nodes.get(player.current_node)
    if node is None or "trade" not in node.affordances:
        return NoAction(agent=player)
    total_gold = sum(getattr(a, "gold", 0) for a in world.agents.values())
    price = node_price(node.stockpile, good, total_gold)
    return BuyAction(
        agent=player, node_id=player.current_node,
        good=good, qty=qty, unit_price=price,
    )


def _make_sell(player, world, good, qty):
    if good is None or qty <= 0:
        return NoAction(agent=player)
    node = world.nodes.get(player.current_node)
    if node is None or "trade" not in node.affordances:
        return NoAction(agent=player)
    total_gold = sum(getattr(a, "gold", 0) for a in world.agents.values())
    price = node_price(node.stockpile, good, total_gold)
    return SellAction(
        agent=player, node_id=player.current_node,
        good=good, qty=qty, unit_price=price,
    )


# ── Quest handling (mirrors adventurer.py, reuses apply_completion) ───────────

def _find_quest(quest_gen, quest_id: str) -> QuestIntent | None:
    for q in getattr(quest_gen, "active_quests", []):
        if q.id == quest_id:
            return q
    return None


def _accept_quest(player, quest_id, world, bus, quest_gen):
    if quest_id is None:
        return NoAction(agent=player)
    quest = _find_quest(quest_gen, quest_id)
    if quest is None or quest.status != "pending" or quest.taker_id is not None:
        return NoAction(agent=player)

    quest_gen.accept(quest.id)
    quest.taker_id = player.id
    player.active_quest_id = quest.id
    player.quest_progress = 0.0
    bus.publish(QuestAccepted(
        tick=world.tick, source="player", severity=EventSeverity.INFO,
        quest_id=quest.id, acceptor=player.id,
    ))
    log.info("[player] accepted quest %s (%s → %s)",
             quest.id, quest.quest_type, quest.target)
    return QuestAcceptAction(
        agent=player, quest_id=quest.id,
        quest_type=quest.quest_type, target=quest.target,
    )


def _work_quest(player, world, bus, quest_gen):
    if player.active_quest_id is None:
        return NoAction(agent=player)
    quest = _find_quest(quest_gen, player.active_quest_id)
    if quest is None or quest.status != "active":
        player.active_quest_id = None
        player.quest_progress = 0.0
        return NoAction(agent=player)

    player.quest_progress += (max(player.skill, 1.0) / _SKILL_BASE) / QUEST_WORK_TICKS
    player.quest_progress = min(1.0, player.quest_progress)
    return QuestProgressAction(
        agent=player, quest_id=quest.id, progress=player.quest_progress,
    )


def _complete_quest(player, world, bus, quest_gen, rng, narrator: QuestNarrator):
    """Resolve the quest via a d20 check. Outcome scales reward and world effect.

    Modifier = stat_modifier(player.skill) (skill→d20 bonus).
    DC       = dc_for_urgency(quest.urgency).
    """
    if player.active_quest_id is None:
        return NoAction(agent=player)
    quest = _find_quest(quest_gen, player.active_quest_id)
    if quest is None or quest.status != "active":
        player.active_quest_id = None
        player.quest_progress = 0.0
        return NoAction(agent=player)
    if player.quest_progress < 1.0:
        return NoAction(agent=player)

    # Roll resolution check
    modifier = stat_modifier(player.skill)
    dc = dc_for_urgency(quest.urgency)
    check = d20_check(rng, modifier, dc)
    mult = outcome_multiplier(check.outcome)

    quest_gen.complete(quest.id)
    effect = apply_completion(quest, world, multiplier=mult)

    reward_base = int(sum(
        qty * BASE_VALUE.get(good, 1.0) for good, qty in quest.reward.items()
    ) * _REWARD_GOLD_MULT)
    reward_gold = max(0, int(round(reward_base * mult)))
    if mult > 0:
        reward_gold = max(1, reward_gold)  # never leave a passing check at 0g
    player.gold += reward_gold
    player.quest_log.append(quest.id)

    # M6 — update faction reputation based on quest supporters
    rep_deltas = apply_quest_completion_reputation(world, quest, player, mult)

    player.active_quest_id = None
    player.quest_progress = 0.0

    # LLM-narrated story beat — stored on the effect so recorder can log it.
    resolution = QuestResolution(
        quest_type=quest.quest_type, target=quest.target, urgency=quest.urgency,
        outcome=check.outcome.value, roll=check.roll, modifier=check.modifier,
        dc=check.dc, total=check.total, reward_gold=reward_gold,
        effect=effect, actor_name=player.name, actor_role="player",
    )
    story = narrator.narrate_resolution(resolution)
    effect = {**effect, "check": check.outcome.value, "roll": check.roll,
              "dc": check.dc, "story": story, "rep_deltas": rep_deltas}

    bus.publish(QuestResolved(
        tick=world.tick, source="player", severity=EventSeverity.INFO,
        quest_id=quest.id, success=check.passed(),
    ))
    log.info("[player] completed quest %s [%s] → %s (+%dg) | %s",
             quest.id, check.outcome.value, effect.get("effect"), reward_gold, story)
    return QuestCompleteAction(
        agent=player, quest_id=quest.id, quest_type=quest.quest_type,
        reward_gold=reward_gold, effect=effect,
    )


# ── Combat ────────────────────────────────────────────────────────────────────

def _fight(player, world, bus, rng: Random):
    """Attack a raider at the player's current node via a d20 check.

    Modifier = stat_modifier(combat_power).
    DC       = 10 + raider.strength/5, so a strength-50 raider is DC 20
               (hard — needs rolls of ≥15 at +5 modifier).
    """
    raiders = [
        a for a in world.agents.values()
        if isinstance(a, RaiderFaction) and a.current_node == player.current_node
    ]
    if not raiders:
        return FightAction(agent=player, target_id="", result="no_target")

    raider = raiders[0]
    durability = player.equipped_weapon.durability if player.equipped_weapon else 0.0
    modifier = stat_modifier(player.combat_power) + int(durability // 10)
    dc = 10 + int(raider.strength / 5)
    check = d20_check(rng, modifier, dc)
    mult = outcome_multiplier(check.outcome)

    base_damage = max(1.0, player.combat_power / 5)   # 1 swing ≈ 7 dmg at cp=35
    if check.passed():
        damage = base_damage * mult
        raider.strength = max(0.0, raider.strength - damage)
        player.needs[NeedType.SAFETY] = max(
            0.0, player.needs.get(NeedType.SAFETY, 0.0) - 0.3 * mult,
        )
        log.info("[player] FIGHT %s [%s] dmg=%.1f (str=%.1f → %.1f)",
                 raider.id, check.outcome.value, damage,
                 raider.strength + damage, raider.strength)
        return FightAction(
            agent=player, target_id=raider.id,
            result=check.outcome.value, damage=damage,
        )
    else:
        loss = min(player.gold, max(1, int((dc - check.total) * 2)))
        player.gold -= loss
        if player.equipped_weapon:
            player.equipped_weapon.durability = max(
                0.0, player.equipped_weapon.durability - 5,
            )
        log.info("[player] FIGHT %s [%s] -%dg", raider.id, check.outcome.value, loss)
        return FightAction(
            agent=player, target_id=raider.id,
            result=check.outcome.value, gold_lost=loss,
        )
