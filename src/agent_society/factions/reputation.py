"""Reputation math + rumor propagation.

Two ingress points:

  apply_quest_completion_reputation(world, quest, player, outcome_mult)
      Updates `player.reputation[faction_id]` when a quest completes. Also
      seeds `known_player_rep` on supporters (they met the player).

  propagate_rumors(world, rng, prob=...)
      Per-tick or per-day. Agents sharing a node have a chance of exchanging
      their known_player_rep. Values drift toward the speaker's with decay.

Agents never see `player.reputation` directly — they only know what reached
them through direct contact or rumor. Pricing/attitude should read
`agent.known_player_rep`, not the player's canonical values.
"""

from __future__ import annotations

from random import Random

from agent_society.schema import PlayerAgent, QuestIntent, World


# Reputation tiers — see CLAUDE.md §M6 design.
REP_TIER = {
    "hero":     60.0,     # ≥ +60 — discount, heroic quest unlock
    "friend":   30.0,     # +30..+60 — friendly dialogue
    "neutral": -30.0,     # -30..+30
    "enemy":   -60.0,     # ≤ -60 — trade refusal, hostile
}

_REP_MIN = -100.0
_REP_MAX = 100.0

# Base reward per quest completion (before urgency/outcome multipliers)
_QUEST_REP_BASE = 10.0
_QUEST_REP_FAILURE = -5.0


def reputation_tier(rep: float) -> str:
    """Classify a rep value into a label for UI / price effects."""
    if rep >= REP_TIER["hero"]:
        return "hero"
    if rep >= REP_TIER["friend"]:
        return "friend"
    if rep <= REP_TIER["enemy"]:
        return "enemy"
    if rep <= REP_TIER["neutral"]:
        return "wary"
    return "neutral"


# ── Quest completion hook ─────────────────────────────────────────────────────

def apply_quest_completion_reputation(
    world: World,
    quest: QuestIntent,
    player: PlayerAgent,
    outcome_mult: float,
) -> dict[str, float]:
    """Update player.reputation for factions represented among supporters.

    Returns {faction_id: delta} for logging. Also seeds the supporters' own
    known_player_rep so they now believe the new value.
    """
    if not quest.supporters:
        return {}

    # Per-faction delta — sum over each supporter's faction
    deltas: dict[str, float] = {}
    base = _QUEST_REP_BASE * (1.0 + quest.urgency) * outcome_mult
    if outcome_mult <= 0:
        # critical_failure — small reputation hit instead
        base = _QUEST_REP_FAILURE

    for aid in quest.supporters:
        agent = world.agents.get(aid)
        if agent is None or agent.faction_id is None:
            continue
        fid = agent.faction_id
        deltas[fid] = deltas.get(fid, 0.0) + base

    # Apply to player
    for fid, delta in deltas.items():
        current = player.reputation.get(fid, 0.0)
        player.reputation[fid] = _clamp(current + delta)

    # Supporters have first-hand knowledge now — overwrite with canonical.
    for aid in quest.supporters:
        agent = world.agents.get(aid)
        if agent is None:
            continue
        for fid, rep in player.reputation.items():
            agent.known_player_rep[fid] = rep

    return {fid: round(d, 1) for fid, d in deltas.items()}


# ── Rumor propagation ─────────────────────────────────────────────────────────

def propagate_rumors(
    world: World,
    rng: Random,
    prob: float = 0.08,
    decay: float = 0.85,
) -> int:
    """Agents at the same node share what they know about the Player.

    Called once per in-game day from the driver. For each node with ≥ 2
    agents, each knower has `prob` chance (per receiver) of passing on their
    reputation map. The receiver's belief moves halfway toward the speaker's
    value, scaled by `decay` so rumor fidelity erodes over hops.

    Returns the number of rumor transfers actually applied.
    """
    transfers = 0
    for node_id, agent_ids in world.agents_by_node.items():
        if len(agent_ids) < 2:
            continue
        knowers = [
            world.agents[aid] for aid in agent_ids
            if aid in world.agents and world.agents[aid].known_player_rep
        ]
        if not knowers:
            continue

        for knower in knowers:
            for other_id in agent_ids:
                if other_id == knower.id or other_id not in world.agents:
                    continue
                if rng.random() > prob:
                    continue
                other = world.agents[other_id]
                for fid, rep in knower.known_player_rep.items():
                    prior = other.known_player_rep.get(fid, 0.0)
                    # Move halfway toward the rumored value, then attenuate.
                    updated = ((prior + rep) / 2.0) * decay
                    other.known_player_rep[fid] = _clamp(updated)
                transfers += 1
    return transfers


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp(v: float) -> float:
    return max(_REP_MIN, min(_REP_MAX, v))
