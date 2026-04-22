"""Economy package — central source of balance configuration and flow models.

Public API:
    from agent_society.economy import CONFIG, BASE_VALUE, NORMAL_STOCKPILE
    from agent_society.economy import net_flow, diagnose, format_diagnosis
    from agent_society.economy import suggest_normal_stockpile, suggest_initial_stockpile
"""

from agent_society.economy.config import (
    BASE_VALUE,
    CONFIG,
    DECAY_RATES,
    FOOD_SATIETY_PER_UNIT,
    NORMAL_STOCKPILE,
    WEAPON_POWER,
    EconomyConfig,
    units_per_meal,
)
from agent_society.economy.equilibrium import (
    apportion_stockpile,
    count_agents,
    diagnose,
    format_diagnosis,
    suggest_baseline_gold,
    suggest_initial_stockpile,
    suggest_normal_stockpile,
    suggest_stockpile_cap,
    suggest_stockpile_caps,
)
from agent_society.economy.flows import (
    FOOD_DEMAND_SHARE,
    ROLE_FLOWS,
    RoleFlow,
    net_flow,
    total_food_consumption,
    total_production,
    total_raw_consumption,
)
from agent_society.economy.routing import (
    CONSUMER_OF,
    PRODUCER_OF,
    charge_consumers,
    distribute_to_producers,
)

__all__ = [
    "BASE_VALUE",
    "CONFIG",
    "CONSUMER_OF",
    "PRODUCER_OF",
    "charge_consumers",
    "distribute_to_producers",
    "DECAY_RATES",
    "EconomyConfig",
    "FOOD_DEMAND_SHARE",
    "FOOD_SATIETY_PER_UNIT",
    "units_per_meal",
    "NORMAL_STOCKPILE",
    "ROLE_FLOWS",
    "RoleFlow",
    "WEAPON_POWER",
    "apportion_stockpile",
    "count_agents",
    "diagnose",
    "format_diagnosis",
    "net_flow",
    "suggest_baseline_gold",
    "suggest_initial_stockpile",
    "suggest_normal_stockpile",
    "suggest_stockpile_cap",
    "suggest_stockpile_caps",
    "total_food_consumption",
    "total_production",
    "total_raw_consumption",
]
