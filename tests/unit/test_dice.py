"""d20 check system — tier boundary tests."""

from __future__ import annotations

from agent_society.game.dice import (
    CheckOutcome,
    d20_check,
    dc_for_urgency,
    outcome_multiplier,
    stat_modifier,
)


class FakeRng:
    """Minimal rng — returns a fixed roll every call. Lets tests hit
    specific outcome boundaries without searching for a real seed."""

    def __init__(self, roll: int) -> None:
        self._roll = roll

    def randint(self, a: int, b: int) -> int:
        return self._roll


def test_natural_20_is_critical_success_regardless_of_dc():
    r = d20_check(FakeRng(20), modifier=-10, dc=100)
    assert r.outcome == CheckOutcome.CRITICAL_SUCCESS
    assert r.is_critical()


def test_natural_1_is_critical_failure_regardless_of_modifier():
    r = d20_check(FakeRng(1), modifier=+50, dc=5)
    assert r.outcome == CheckOutcome.CRITICAL_FAILURE
    assert r.is_critical()
    assert not r.passed()


def test_success_requires_beating_dc_by_five():
    # total = 15 + 5 = 20, dc = 15 → 20 >= dc+5 → success
    r = d20_check(FakeRng(15), modifier=5, dc=15)
    assert r.outcome == CheckOutcome.SUCCESS
    assert r.passed()


def test_partial_meets_dc_but_not_by_five():
    # total = 10 + 5 = 15, dc = 14 → meet, but not beat by 5 → partial
    r = d20_check(FakeRng(10), modifier=5, dc=14)
    assert r.outcome == CheckOutcome.PARTIAL
    assert r.passed()


def test_failure_below_dc():
    r = d20_check(FakeRng(5), modifier=0, dc=15)
    assert r.outcome == CheckOutcome.FAILURE
    assert not r.passed()


def test_stat_modifier_around_midpoint():
    assert stat_modifier(50) == 0
    assert stat_modifier(70) == 2
    assert stat_modifier(30) == -2


def test_stat_modifier_is_clamped():
    assert stat_modifier(500) <= 10
    assert stat_modifier(-500) >= -5


def test_outcome_multiplier_ordering():
    """Multiplier decreases monotonically from crit_success to crit_failure."""
    ordered = [
        outcome_multiplier(CheckOutcome.CRITICAL_SUCCESS),
        outcome_multiplier(CheckOutcome.SUCCESS),
        outcome_multiplier(CheckOutcome.PARTIAL),
        outcome_multiplier(CheckOutcome.FAILURE),
        outcome_multiplier(CheckOutcome.CRITICAL_FAILURE),
    ]
    assert ordered == sorted(ordered, reverse=True)
    assert outcome_multiplier(CheckOutcome.CRITICAL_FAILURE) == 0.0


def test_dc_for_urgency_bounds():
    assert dc_for_urgency(0.0) == 10
    assert dc_for_urgency(1.0) == 18
    # monotonic
    assert dc_for_urgency(0.5) > dc_for_urgency(0.2)


def test_narrator_resolution_uses_outcome_label():
    from agent_society.llm.base import QuestResolution
    from agent_society.llm.mock_backend import MockNarrator

    res = QuestResolution(
        quest_type="raider_suppress", target="raider", urgency=0.9,
        outcome="critical_success", roll=20, modifier=3, dc=18, total=23,
        reward_gold=42, effect={"effect": "raider_suppress"},
        actor_name="Hero", actor_role="player",
    )
    story = MockNarrator().narrate_resolution(res)
    assert "대성공" in story
    assert "Hero" in story
