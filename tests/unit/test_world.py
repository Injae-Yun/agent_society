"""Smoke tests for world state management and WorldSnapshot."""

from __future__ import annotations

import pytest

from agent_society.schema import Agent, NeedType, Role
from agent_society.world import world as world_ops
from agent_society.world.snapshot import WorldSnapshot


def test_build_indices(mini_world):
    assert "farmer_1" in mini_world.agents_by_node["farm.hub"]
    assert "merchant_1" in mini_world.agents_by_role[Role.MERCHANT]
    assert "blacksmith_1" in mini_world.agents_by_role[Role.BLACKSMITH]


def test_add_agent(mini_world):
    new_agent = Agent("miner_99", "Miner X", Role.MINER, "farm.hub", "farm.hub")
    world_ops.add_agent(mini_world, new_agent)
    assert "miner_99" in mini_world.agents
    assert "miner_99" in mini_world.agents_by_node["farm.hub"]
    assert "miner_99" in mini_world.agents_by_role[Role.MINER]


def test_add_duplicate_agent_raises(mini_world):
    dup = Agent("farmer_1", "Dup", Role.FARMER, "farm.hub", "farm.hub")
    with pytest.raises(ValueError, match="already exists"):
        world_ops.add_agent(mini_world, dup)


def test_remove_agent(mini_world):
    removed = world_ops.remove_agent(mini_world, "farmer_1")
    assert removed.id == "farmer_1"
    assert "farmer_1" not in mini_world.agents
    assert "farmer_1" not in mini_world.agents_by_node.get("farm.hub", [])
    assert "farmer_1" not in mini_world.agents_by_role.get(Role.FARMER, [])


def test_move_agent_updates_indices(mini_world):
    world_ops.move_agent(mini_world, "farmer_1", "city.market")
    assert mini_world.agents["farmer_1"].current_node == "city.market"
    assert "farmer_1" in mini_world.agents_by_node["city.market"]
    assert "farmer_1" not in mini_world.agents_by_node.get("farm.hub", [])


def test_move_agent_invalid_node(mini_world):
    with pytest.raises(ValueError, match="does not exist"):
        world_ops.move_agent(mini_world, "farmer_1", "nonexistent.node")


def test_agents_at(mini_world):
    at_hub = world_ops.agents_at(mini_world, "farm.hub")
    ids = [a.id for a in at_hub]
    assert "farmer_1" in ids


def test_edges_from_excludes_severed(mini_world):
    mini_world.edges[0].severed = True
    edges = world_ops.edges_from(mini_world, "city.market")
    assert len(edges) == 0


def test_scarcity_increases_with_lower_stock(mini_world):
    mini_world.nodes["city.market"].stockpile["wheat"] = 100
    low = world_ops.scarcity(mini_world, "wheat")
    mini_world.nodes["city.market"].stockpile["wheat"] = 1
    high = world_ops.scarcity(mini_world, "wheat")
    assert high > low


# ── WorldSnapshot ─────────────────────────────────────────────────────────────

def test_snapshot_read_ops(mini_world):
    snap = WorldSnapshot(mini_world)
    assert snap.tick == 0
    assert snap.get_node("city.market").name == "Market"
    assert snap.get_agent("farmer_1").role == Role.FARMER
    assert len(snap.agents_at("farm.hub")) == 1


def test_snapshot_write_raises(mini_world):
    snap = WorldSnapshot(mini_world)
    with pytest.raises(AttributeError):
        snap.tick = 999  # type: ignore[misc]


def test_snapshot_scarcity(mini_world):
    snap = WorldSnapshot(mini_world)
    s = snap.scarcity("wheat")
    assert s > 0
