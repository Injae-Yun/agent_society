"""Role catalog — defines what each role produces and what tools it needs."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_society.schema import NeedType, Role


@dataclass
class RoleDef:
    role: Role
    primary_good: str
    required_tools: list[str]
    available_action_types: list[str]
    home_region: str
    # Need that rises when primary tool wears down
    tool_need_type: NeedType = NeedType.TOOL_NEED
    # How much need satisfying food gives (hunger)
    hunger_satisfy: float = 0.5


ROLE_CATALOG: dict[Role, RoleDef] = {
    Role.FARMER: RoleDef(
        role=Role.FARMER,
        primary_good="wheat",
        required_tools=["plow", "sickle"],
        available_action_types=["produce", "consume_food", "trade"],
        home_region="farmland",
    ),
    Role.HERDER: RoleDef(
        role=Role.HERDER,
        primary_good="meat",
        required_tools=["sickle"],
        available_action_types=["produce", "consume_food", "trade"],
        home_region="farmland",
    ),
    Role.MINER: RoleDef(
        role=Role.MINER,
        primary_good="ore",
        required_tools=["pickaxe"],
        available_action_types=["produce", "consume_food", "trade"],
        home_region="farmland",
    ),
    Role.ORCHARDIST: RoleDef(
        role=Role.ORCHARDIST,
        primary_good="fruit",
        required_tools=["pruning_shears", "ladder"],
        available_action_types=["produce", "consume_food", "trade"],
        home_region="farmland",
    ),
    Role.BLACKSMITH: RoleDef(
        role=Role.BLACKSMITH,
        primary_good="sword",  # or tools — selection logic picks based on demand
        required_tools=["hammer"],
        available_action_types=["craft", "consume_food", "trade"],
        home_region="city",
    ),
    Role.COOK: RoleDef(
        role=Role.COOK,
        primary_good="cooked_meal",
        required_tools=["cooking_tools"],
        available_action_types=["craft", "consume_food", "trade"],
        home_region="city",
    ),
    Role.MERCHANT: RoleDef(
        role=Role.MERCHANT,
        primary_good="",  # no primary production
        required_tools=["cart"],
        available_action_types=["trade", "travel", "consume_food"],
        home_region="city",
    ),
    Role.RAIDER: RoleDef(
        role=Role.RAIDER,
        primary_good="",
        required_tools=["sword"],
        available_action_types=["raid", "travel", "consume_food"],
        home_region="raider_base",
    ),
}
