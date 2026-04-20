"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from agent_society.events.bus import WorldEventBus
from agent_society.llm.mock_backend import MockNarrator
from agent_society.schema import Agent, Edge, NeedType, Node, RegionType, Role, World
from agent_society.world.world import build_indices


@pytest.fixture
def mock_bus() -> WorldEventBus:
    return WorldEventBus()


@pytest.fixture
def mock_narrator() -> MockNarrator:
    return MockNarrator()


@pytest.fixture
def mini_world() -> World:
    """3-agent, 3-node minimal world for fast unit tests."""
    nodes = {
        "city.market": Node("city.market", "Market", RegionType.CITY, stockpile={"wheat": 10}),
        "farm.hub": Node("farm.hub", "Farm Hub", RegionType.FARMLAND, stockpile={"meat": 5}),
        "raider.hideout": Node("raider.hideout", "Hideout", RegionType.RAIDER_BASE),
    }
    edges = [
        Edge("city.market", "farm.hub", travel_cost=10, base_threat=0.3, capacity=2),
    ]
    agents = {
        "farmer_1": Agent("farmer_1", "Farmer", Role.FARMER, "farm.hub", "farm.hub",
                          needs={NeedType.HUNGER: 0.2}),
        "merchant_1": Agent("merchant_1", "Merchant", Role.MERCHANT, "city.market", "city.market",
                            needs={NeedType.HUNGER: 0.1}, inventory={"wheat": 3}),
        "blacksmith_1": Agent("blacksmith_1", "Blacksmith", Role.BLACKSMITH, "city.market", "city.market"),
    }
    world = World(nodes=nodes, edges=edges, agents=agents)
    build_indices(world)
    return world
