"""Smoke tests for needs decay and urgency."""

from __future__ import annotations

from agent_society.agents.needs import decay_needs, is_urgent, need_urgency, satisfy_need
from agent_society.config.balance import DECAY_RATES
from agent_society.config.parameters import URGENCY_THRESHOLD
from agent_society.schema import Agent, NeedType, Role


def _agent(needs: dict | None = None) -> Agent:
    return Agent("a1", "Test", Role.FARMER, "farm.hub", "farm.hub",
                 needs=needs or {})


def test_decay_increases_hunger():
    agent = _agent({NeedType.HUNGER: 0.0})
    decay_needs(agent)
    assert agent.needs[NeedType.HUNGER] == pytest.approx(DECAY_RATES[NeedType.HUNGER])


def test_decay_clamps_at_one():
    agent = _agent({NeedType.HUNGER: 0.999})
    decay_needs(agent, dt=100)
    assert agent.needs[NeedType.HUNGER] == 1.0


def test_decay_dt_multiplier():
    agent = _agent({NeedType.HUNGER: 0.0})
    decay_needs(agent, dt=5)
    expected = DECAY_RATES[NeedType.HUNGER] * 5
    assert agent.needs[NeedType.HUNGER] == pytest.approx(expected)


def test_need_urgency_max():
    agent = _agent({NeedType.HUNGER: 0.3, NeedType.SAFETY: 0.8})
    assert need_urgency(agent) == pytest.approx(0.8)


def test_is_urgent_threshold():
    agent = _agent({NeedType.HUNGER: URGENCY_THRESHOLD - 0.01})
    assert not is_urgent(agent)
    agent.needs[NeedType.HUNGER] = URGENCY_THRESHOLD
    assert is_urgent(agent)


def test_satisfy_need():
    agent = _agent({NeedType.HUNGER: 0.8})
    satisfy_need(agent, NeedType.HUNGER, 0.5)
    assert agent.needs[NeedType.HUNGER] == pytest.approx(0.3)


def test_satisfy_need_clamps_at_zero():
    agent = _agent({NeedType.HUNGER: 0.1})
    satisfy_need(agent, NeedType.HUNGER, 1.0)
    assert agent.needs[NeedType.HUNGER] == 0.0


import pytest
