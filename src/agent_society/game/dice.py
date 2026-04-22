"""d20 check system — DnD-style 1d20 + modifier vs. difficulty class.

Usage:
    result = d20_check(rng, modifier=+5, dc=15)
    if result.outcome == CheckOutcome.CRITICAL_SUCCESS: ...

Outcome tiers:
    roll == 20           → critical_success  (regardless of DC)
    total >= dc + 5      → success
    total >= dc          → partial
    total <  dc          → failure
    roll == 1            → critical_failure  (regardless of DC)

Character stats map to the modifier through `stat_modifier()`. The
`outcome_multiplier()` helper converts an outcome to a reward scaling
factor — used by quest completion, combat damage, and future effect
handlers to soften or amplify results.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import Random


class CheckOutcome(Enum):
    CRITICAL_SUCCESS = "critical_success"
    SUCCESS          = "success"
    PARTIAL          = "partial"
    FAILURE          = "failure"
    CRITICAL_FAILURE = "critical_failure"


@dataclass(frozen=True)
class CheckResult:
    roll: int         # 1..20 (the raw d20)
    modifier: int     # stat-derived bonus
    dc: int           # difficulty class (target to meet or beat)
    total: int        # roll + modifier
    outcome: CheckOutcome

    def passed(self) -> bool:
        return self.outcome in (
            CheckOutcome.CRITICAL_SUCCESS,
            CheckOutcome.SUCCESS,
            CheckOutcome.PARTIAL,
        )

    def is_critical(self) -> bool:
        return self.outcome in (
            CheckOutcome.CRITICAL_SUCCESS, CheckOutcome.CRITICAL_FAILURE,
        )


# ── Core API ──────────────────────────────────────────────────────────────────

def d20_check(rng: Random, modifier: int, dc: int) -> CheckResult:
    """Roll 1d20 + modifier against `dc`. Returns a `CheckResult`."""
    roll = rng.randint(1, 20)
    total = roll + modifier
    if roll == 20:
        outcome = CheckOutcome.CRITICAL_SUCCESS
    elif roll == 1:
        outcome = CheckOutcome.CRITICAL_FAILURE
    elif total >= dc + 5:
        outcome = CheckOutcome.SUCCESS
    elif total >= dc:
        outcome = CheckOutcome.PARTIAL
    else:
        outcome = CheckOutcome.FAILURE
    return CheckResult(roll=roll, modifier=modifier, dc=dc, total=total, outcome=outcome)


# ── Helpers — stat → modifier, outcome → reward scaling ──────────────────────

def stat_modifier(stat_value: float, midpoint: float = 50.0, scale: float = 10.0) -> int:
    """Convert a 0..100 stat (skill, combat_power, etc.) to a d20 modifier.

    midpoint=50 → +0. scale=10 → every 10 stat points above mid = +1.
    Result capped to roughly [-5, +10].
    """
    raw = (stat_value - midpoint) / scale
    return max(-5, min(10, int(round(raw))))


def dc_for_urgency(urgency: float, base: int = 10, slope: int = 8) -> int:
    """Quest urgency 0..1 → DC 10..18 (harder the more urgent)."""
    return base + int(round(urgency * slope))


# Reward/effect multiplier by outcome — used by quest completion and combat.
_OUTCOME_MULT: dict[CheckOutcome, float] = {
    CheckOutcome.CRITICAL_SUCCESS: 1.5,
    CheckOutcome.SUCCESS:          1.0,
    CheckOutcome.PARTIAL:          0.7,
    CheckOutcome.FAILURE:          0.3,
    CheckOutcome.CRITICAL_FAILURE: 0.0,
}


def outcome_multiplier(outcome: CheckOutcome) -> float:
    return _OUTCOME_MULT.get(outcome, 1.0)
