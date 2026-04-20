"""Good type definitions and tier classification."""

from __future__ import annotations

from agent_society.config.balance import BASE_VALUE
from agent_society.schema import Tier

FOOD_GOODS: set[str] = {"wheat", "meat", "fruit", "cooked_meal"}
BASIC_FOOD: set[str] = {"wheat", "meat"}
PREMIUM_FOOD: set[str] = {"fruit", "cooked_meal"}
RAW_MATERIALS: set[str] = {"ore"}
TOOLS: set[str] = {"plow", "sickle", "pickaxe", "pruning_shears", "ladder", "hammer", "cooking_tools", "cart"}
WEAPONS: set[str] = {"sword", "bow"}


def tier_of(good: str) -> Tier:
    if good in PREMIUM_FOOD:
        return Tier.PREMIUM
    return Tier.BASIC


def base_value(good: str) -> float:
    return BASE_VALUE.get(good, 1.0)
