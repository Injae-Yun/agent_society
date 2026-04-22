"""Central economic configuration — single source of truth for all balance knobs.

Everything that was previously scattered across `config/balance.py`,
`agents/actions.py`, `agents/selection.py`, and scenario YAMLs lives here.

Usage:
    from agent_society.economy.config import CONFIG, BASE_VALUE, NORMAL_STOCKPILE

    food_hunger_relief = CONFIG.food_satisfy_hunger
    cap = CONFIG.farm_stock_cap

The companion modules `flows.py` and `equilibrium.py` use these values to
derive per-tick production/consumption rates and suggest stockpile levels
for any given agent population.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_society.schema import NeedType


# ════════════════════════════════════════════════════════════════════════════
#  Tuning knobs — everything the designer may want to tweak
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class EconomyConfig:   # not frozen — builder may re-tune at world construction
    # ── Needs decay (per tick) ────────────────────────────────────────────────
    hunger_decay: float = 0.10              # hungry in ~8 ticks (3 meals/day)
    food_satisfaction_decay: float = 0.04   # satiety ~1 day
    tool_need_decay: float = 0.2            # only spikes on break
    safety_decay: float = 0.010             # recover in ~4 days after raid
    food_satisfy_hunger: float = 0.5        # hunger reduction per meal
    premium_food_sat_bonus: float = 0.5     # fruit/cooked_meal bonus
    tool_need_spike_on_break: float = 0.3
    urgency_threshold: float = 0.7          # quest trigger level

    # ── Production / crafting ─────────────────────────────────────────────────
    produce_amount_per_action: int = 1
    produce_wage_coef: float = 0.50         # gold = BASE_VALUE × coef × units
    inv_wage_cap: int = 3                   # max personal inv from wage
    tool_decay_per_action: float = 0.05      # ~100 actions per tool
    tool_max_durability: float = 10.0

    # ── Market pricing ────────────────────────────────────────────────────────
    scarcity_k: float = 2.0                 # price swing: max 3× BASE at empty
    baseline_gold: int = 800                # inflation_factor = 1.0 at this total
    inflation_cap: float = 3.0
    inflation_floor: float = 0.5
    merchant_min_margin: float = 0.5        # gold/unit profit threshold

    # ── Raid ──────────────────────────────────────────────────────────────────
    raid_rate: float = 0.4
    raid_destruction: float = 0.15
    strength_gain_success: float = 2.0
    strength_loss_failure: float = 3.0
    strength_loss_base_attack: float = 20.0
    strength_starvation_daily: float = 1.0

    # ── Selection thresholds (used by agents/selection.py) ────────────────────
    farm_stock_cap: int = 80                # producers stop when node full
    merchant_carry_cap: int = 10
    merchant_gold_reserve: int = 5     # keep this much spare to cover travel meals
    city_demand_cap: int = 30               # merchant skips shipping if city ≥ this

    # ── Initial agent gold ────────────────────────────────────────────────────
    merchant_initial_gold: int = 80
    producer_initial_gold: int = 20
    node_initial_gold: int = 100

    # ── Events ────────────────────────────────────────────────────────────────
    harvest_boom_multiplier: float = 1.5
    harvest_failure_multiplier: float = 0.5
    plague_productivity_penalty: float = 0.30

    # ── Gold tax (inflation sink) ─────────────────────────────────────────────
    gold_tax_threshold: int = 2000
    gold_tax_rate: float = 0.20


CONFIG = EconomyConfig()


# ════════════════════════════════════════════════════════════════════════════
#  Good-specific tables
# ════════════════════════════════════════════════════════════════════════════

# Base barter value relative to wheat = 1.0
BASE_VALUE: dict[str, float] = {
    "wheat":          1.0,
    "meat":           1.0,
    "fruit":          2.0,
    "cooked_meal":    3.0,
    "ore":            5.0,
    "plow":           5.0,
    "sickle":         6.0,
    "pickaxe":        8.0,
    "pruning_shears": 6.0,
    "cooking_tools":  8.0,
    "cart":          10.0,
    "sword":          8.0,
    "bow":            6.0,
}

WEAPON_POWER: dict[str, int] = {
    "sword": 30,
    "bow":   20,
}

# "Normal" stockpile — price == BASE_VALUE at this level. Populated here as a
# per-good baseline; `equilibrium.suggest_normal_stockpile(agent_counts)` can
# override this with values sized to the actual population.
NORMAL_STOCKPILE: dict[str, int] = {
    "wheat":          20,
    "meat":           15,
    "fruit":          10,
    "cooked_meal":    10,
    "ore":            15,
    "sword":           4,
    "plow":            8,
    "sickle":          4,
    "pickaxe":         4,
    "pruning_shears":  3,
    "cooking_tools":   3,
    "cart":            2,
    "bow":             3,
}


# ── Food satiety (how much hunger 1 unit of food relieves) ────────────────────
# A "meal" refills CONFIG.food_satisfy_hunger (0.5) of hunger. Raw staples are
# less calorie-dense, so agents must eat several units per meal — which drives
# demand proportionally for primary producers.

FOOD_SATIETY_PER_UNIT: dict[str, float] = {
    "cooked_meal": 0.50,   # 1 unit = 1 meal (processed, convenient)
    "fruit":       0.25,   # 2 units = 1 meal
    "meat":        0.25,   # 2 units = 1 meal
    "wheat":       0.25,   # 2 units = 1 meal (raw grain)
}


def units_per_meal(food: str) -> int:
    """How many units of `food` are needed for one full meal."""
    satiety = FOOD_SATIETY_PER_UNIT.get(food, CONFIG.food_satisfy_hunger)
    if satiety <= 0:
        return 1
    import math
    return max(1, math.ceil(CONFIG.food_satisfy_hunger / satiety))


# ════════════════════════════════════════════════════════════════════════════
#  Derived / legacy aliases (kept for existing imports)
# ════════════════════════════════════════════════════════════════════════════

DECAY_RATES: dict[NeedType, float] = {
    NeedType.HUNGER:             CONFIG.hunger_decay,
    NeedType.FOOD_SATISFACTION:  CONFIG.food_satisfaction_decay,
    NeedType.TOOL_NEED:          CONFIG.tool_need_decay,
    NeedType.SAFETY:             CONFIG.safety_decay,
}

# Flat re-exports (match old config/balance.py names) ─────────────────────────
SCARCITY_K               = CONFIG.scarcity_k
BASELINE_GOLD            = CONFIG.baseline_gold
INFLATION_CAP            = CONFIG.inflation_cap
INFLATION_FLOOR          = CONFIG.inflation_floor
MERCHANT_MIN_MARGIN      = CONFIG.merchant_min_margin
MERCHANT_INITIAL_GOLD    = CONFIG.merchant_initial_gold
PRODUCER_INITIAL_GOLD    = CONFIG.producer_initial_gold
NODE_INITIAL_GOLD        = CONFIG.node_initial_gold
PRODUCE_WAGE             = CONFIG.produce_wage_coef
RAID_RATE                = CONFIG.raid_rate
DESTRUCTION_FACTOR       = CONFIG.raid_destruction
STRENGTH_GAIN_FROM_SUCCESS  = CONFIG.strength_gain_success
STRENGTH_LOSS_FROM_FAILURE  = CONFIG.strength_loss_failure
STRENGTH_LOSS_FROM_BASE_ATTACK = CONFIG.strength_loss_base_attack
STRENGTH_STARVATION_DECAY = CONFIG.strength_starvation_daily
HARVEST_BOOM_MULTIPLIER  = CONFIG.harvest_boom_multiplier
HARVEST_FAILURE_MULTIPLIER = CONFIG.harvest_failure_multiplier
PLAGUE_PRODUCTIVITY_PENALTY = CONFIG.plague_productivity_penalty
GOLD_TAX_THRESHOLD       = CONFIG.gold_tax_threshold
GOLD_TAX_RATE            = CONFIG.gold_tax_rate
