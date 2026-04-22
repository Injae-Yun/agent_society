"""Per-role production / consumption rate model.

Each role's behaviour is boiled down to average per-tick flow rates so the
equilibrium solver can compute total world throughput from raw agent counts.

These numbers are **analytic estimates** based on `selection.py` priorities
(utility scores, hunger decay, tool decay). They are not exact; the solver
is resilient to moderate error because the pricing system self-corrects as
stockpiles drift.

Tweak here, not in scenario YAMLs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_society.economy.config import CONFIG
from agent_society.schema import Role

# ── Derived constants ─────────────────────────────────────────────────────────
# Produce activity rate: a producer spends this fraction of ticks actually
# producing (rest is eating, travel, tool acquisition).
_PRODUCE_ACTIVITY = 0.85

# Eat rate: hunger hits 0.5 threshold every ~1/hunger_decay×0.5 ticks.
# CONFIG.hunger_decay 0.06 → ~8.3 ticks per meal → 0.12 meals/tick.
_MEALS_PER_TICK = CONFIG.food_satisfy_hunger * CONFIG.hunger_decay  # 0.5 * 0.06 = 0.03
# Correction: hunger decays at 0.06/tick, eating removes 0.5. Cycle length ~ 8.3t,
# so meals per tick = 1 / 8.33 ≈ 0.12. Formula: decay / satisfy = wrong.
# Use 1 / (satisfy / decay) = decay / satisfy = 0.12
_MEALS_PER_TICK = CONFIG.hunger_decay / CONFIG.food_satisfy_hunger  # 0.06/0.5 = 0.12

# Tool usage: CONFIG.tool_decay_per_action = 0.1, max 10.0 → 100 actions/tool.
# Tool replacement rate per producer = produce_activity / 100 = 0.007/tick.
_TOOL_WEAR_RATE = _PRODUCE_ACTIVITY * CONFIG.tool_decay_per_action / CONFIG.tool_max_durability


# ── Per-role flow spec ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RoleFlow:
    role: Role
    # Per-tick production (positive-value goods output).
    produces: dict[str, float] = field(default_factory=dict)
    # Per-tick raw-material / tool consumption (not counting meals).
    consumes: dict[str, float] = field(default_factory=dict)
    # Per-tick meals eaten; allocated to food goods via FOOD_DEMAND_SHARE.
    meals_per_tick: float = 0.0


# Food preference share — how 1 meal is split across food goods (in aggregate).
# Agents prefer cooked_meal > fruit > meat > wheat, but availability varies.
FOOD_DEMAND_SHARE: dict[str, float] = {
    "cooked_meal": 0.30,
    "fruit":       0.15,
    "meat":        0.25,
    "wheat":       0.30,
}


# Cook recipe mix (what fraction of crafts use each recipe)
# Recipes lightened: wheat 1 + meat 1 dominant, fallback wheat-only uses 2.
_COOK_RECIPE_WHEAT_MEAT  = 0.60   # 1 wheat + 1 meat
_COOK_RECIPE_WHEAT_FRUIT = 0.30   # 1 wheat + 1 fruit
_COOK_RECIPE_WHEAT_ONLY  = 0.10   # 2 wheat (starvation fallback)

_COOK_CRAFTS_PER_TICK = 0.4   # observed from `_select_cook` utility scoring

_COOK_WHEAT_RATE = _COOK_CRAFTS_PER_TICK * (
    _COOK_RECIPE_WHEAT_MEAT * 1 + _COOK_RECIPE_WHEAT_FRUIT * 1 + _COOK_RECIPE_WHEAT_ONLY * 2
)
_COOK_MEAT_RATE  = _COOK_CRAFTS_PER_TICK * _COOK_RECIPE_WHEAT_MEAT * 1
_COOK_FRUIT_RATE = _COOK_CRAFTS_PER_TICK * _COOK_RECIPE_WHEAT_FRUIT * 1

# Blacksmith output mix (scarcity-gated; averaged across categories)
_BS_CRAFTS_PER_TICK = 0.45
_BS_MIX = {
    "sword":          0.18,
    "plow":           0.18,
    "sickle":         0.16,
    "pickaxe":        0.16,
    "cooking_tools":  0.16,
    "pruning_shears": 0.16,
}
_BS_ORE_PER_CRAFT = {
    "sword": 2, "plow": 2, "sickle": 1, "pickaxe": 1,
    "cooking_tools": 1, "pruning_shears": 1,
}
_BS_ORE_RATE = _BS_CRAFTS_PER_TICK * sum(
    _BS_MIX[g] * _BS_ORE_PER_CRAFT[g] for g in _BS_MIX
)


ROLE_FLOWS: dict[Role, RoleFlow] = {
    Role.FARMER: RoleFlow(
        role=Role.FARMER,
        produces={"wheat": _PRODUCE_ACTIVITY},
        consumes={"plow": _TOOL_WEAR_RATE, "sickle": _TOOL_WEAR_RATE * 0.3},
        meals_per_tick=_MEALS_PER_TICK,
    ),
    Role.HERDER: RoleFlow(
        role=Role.HERDER,
        produces={"meat": _PRODUCE_ACTIVITY},
        consumes={"sickle": _TOOL_WEAR_RATE},
        meals_per_tick=_MEALS_PER_TICK,
    ),
    Role.MINER: RoleFlow(
        role=Role.MINER,
        produces={"ore": _PRODUCE_ACTIVITY},
        consumes={"pickaxe": _TOOL_WEAR_RATE},
        meals_per_tick=_MEALS_PER_TICK,
    ),
    Role.ORCHARDIST: RoleFlow(
        role=Role.ORCHARDIST,
        produces={"fruit": _PRODUCE_ACTIVITY},
        consumes={"pruning_shears": _TOOL_WEAR_RATE},
        meals_per_tick=_MEALS_PER_TICK,
    ),
    Role.BLACKSMITH: RoleFlow(
        role=Role.BLACKSMITH,
        produces={g: _BS_CRAFTS_PER_TICK * share for g, share in _BS_MIX.items()},
        consumes={"ore": _BS_ORE_RATE},
        meals_per_tick=_MEALS_PER_TICK,
    ),
    Role.COOK: RoleFlow(
        role=Role.COOK,
        produces={"cooked_meal": _COOK_CRAFTS_PER_TICK},
        consumes={
            "wheat":         _COOK_WHEAT_RATE,
            "meat":          _COOK_MEAT_RATE,
            "fruit":         _COOK_FRUIT_RATE,
            "cooking_tools": _TOOL_WEAR_RATE * 0.5,
        },
        meals_per_tick=_MEALS_PER_TICK,
    ),
    Role.MERCHANT: RoleFlow(
        role=Role.MERCHANT,
        produces={},
        consumes={},
        meals_per_tick=_MEALS_PER_TICK,
    ),
    Role.RAIDER: RoleFlow(
        role=Role.RAIDER,
        produces={},
        consumes={},
        meals_per_tick=_MEALS_PER_TICK * 0.5,   # raiders eat less, skip safety
    ),
}


# ── Aggregation helpers ───────────────────────────────────────────────────────

def total_production(agent_counts: dict[Role, int]) -> dict[str, float]:
    """Sum of per-role production rates for a given population."""
    out: dict[str, float] = {}
    for role, n in agent_counts.items():
        flow = ROLE_FLOWS.get(role)
        if flow is None or n <= 0:
            continue
        for good, rate in flow.produces.items():
            out[good] = out.get(good, 0.0) + rate * n
    return out


def total_raw_consumption(agent_counts: dict[Role, int]) -> dict[str, float]:
    """Tool + crafting ingredient consumption (excludes meals)."""
    out: dict[str, float] = {}
    for role, n in agent_counts.items():
        flow = ROLE_FLOWS.get(role)
        if flow is None or n <= 0:
            continue
        for good, rate in flow.consumes.items():
            out[good] = out.get(good, 0.0) + rate * n
    return out


def total_food_consumption(agent_counts: dict[Role, int]) -> dict[str, float]:
    """Per-tick *unit* demand per food good.

    Raw staples need multiple units per meal (see `units_per_meal`), so wheat
    demand is 3× its meal-share, fruit/meat 2×, cooked_meal 1×. This is what
    drives the normal-stockpile sizing and the merchant's buy/sell signals.
    """
    from agent_society.economy.config import units_per_meal
    total_meals = sum(
        (ROLE_FLOWS[r].meals_per_tick if r in ROLE_FLOWS else 0.0) * n
        for r, n in agent_counts.items()
    )
    return {
        good: total_meals * share * units_per_meal(good)
        for good, share in FOOD_DEMAND_SHARE.items()
    }


def net_flow(agent_counts: dict[Role, int]) -> dict[str, float]:
    """Production minus (raw + food) consumption per tick.

    Positive = surplus, negative = deficit.
    """
    prod = total_production(agent_counts)
    raw  = total_raw_consumption(agent_counts)
    food = total_food_consumption(agent_counts)
    goods = set(prod) | set(raw) | set(food)
    return {g: prod.get(g, 0.0) - raw.get(g, 0.0) - food.get(g, 0.0) for g in goods}
