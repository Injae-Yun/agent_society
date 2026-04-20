"""Needs decay and urgency calculation."""

from __future__ import annotations

from agent_society.config.balance import DECAY_RATES
from agent_society.config.parameters import URGENCY_THRESHOLD
from agent_society.schema import Agent, NeedType


# Needs that represent deprivation — grow toward 1.0 over time.
_GROWING_NEEDS = {NeedType.HUNGER, NeedType.FOOD_SATISFACTION, NeedType.TOOL_NEED}
# Needs that are threat memories — spike up and fade toward 0 over time.
_DECAYING_NEEDS = {NeedType.SAFETY}


def decay_needs(agent: Agent, dt: int = 1) -> None:
    """Tick all needs. Deprivation needs grow; threat-memory needs decay.

    HUNGER / FOOD_SATISFACTION / TOOL_NEED: grow toward 1.0 (full deprivation).
    SAFETY: fades toward 0.0 (memory of past threats gradually disappears).
    """
    for need_type, rate in DECAY_RATES.items():
        current = agent.needs.get(need_type, 0.0)
        if need_type in _DECAYING_NEEDS:
            agent.needs[need_type] = max(0.0, current - rate * dt)
        else:
            agent.needs[need_type] = min(1.0, current + rate * dt)


def need_urgency(agent: Agent) -> float:
    """Max need value across all NeedTypes — used to decide Quest triggering."""
    if not agent.needs:
        return 0.0
    return max(agent.needs.values())


def is_urgent(agent: Agent) -> bool:
    return need_urgency(agent) >= URGENCY_THRESHOLD


def satisfy_need(agent: Agent, need_type: NeedType, amount: float) -> None:
    """Reduce a need by amount. Clamps to 0."""
    current = agent.needs.get(need_type, 0.0)
    agent.needs[need_type] = max(0.0, current - amount)
