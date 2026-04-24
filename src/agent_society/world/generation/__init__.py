"""Procedural map generation (M7b+).

Separate package from `world/pieces` (static library of templates) because
this code is about assembling them — Voronoi, routes, population seeding.

Public API:
    from agent_society.world.generation import place_roads, RoadPlan
"""

from agent_society.world.generation.biomes import (
    DEFAULT_BIOME_WEIGHTS,
    assign_biomes,
)
from agent_society.world.generation.generator import (
    GenerationParams,
    GenerationReport,
    generate_world,
)
from agent_society.world.generation.lairs import LairPlacement, place_raider_lair
from agent_society.world.generation.risk import paint_raid_risk
from agent_society.world.generation.roads import RoadPlan, place_roads
from agent_society.world.generation.territory import assign_territory

__all__ = [
    "DEFAULT_BIOME_WEIGHTS",
    "GenerationParams",
    "GenerationReport",
    "LairPlacement",
    "RoadPlan",
    "assign_biomes",
    "assign_territory",
    "generate_world",
    "paint_raid_risk",
    "place_raider_lair",
    "place_roads",
]
