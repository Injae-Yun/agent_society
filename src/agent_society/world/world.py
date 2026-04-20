"""World state management — mutation methods and index maintenance."""

from __future__ import annotations

from agent_society.schema import Agent, Node, Role, World


def build_indices(world: World) -> None:
    """Rebuild agents_by_node and agents_by_role from scratch."""
    world.agents_by_node = {node_id: [] for node_id in world.nodes}
    world.agents_by_role = {role: [] for role in Role}
    for agent_id, agent in world.agents.items():
        world.agents_by_node.setdefault(agent.current_node, []).append(agent_id)
        world.agents_by_role.setdefault(agent.role, []).append(agent_id)


def add_agent(world: World, agent: Agent) -> None:
    if agent.id in world.agents:
        raise ValueError(f"Agent {agent.id!r} already exists")
    world.agents[agent.id] = agent
    world.agents_by_node.setdefault(agent.current_node, []).append(agent.id)
    world.agents_by_role.setdefault(agent.role, []).append(agent.id)


def remove_agent(world: World, agent_id: str) -> Agent:
    agent = world.agents.pop(agent_id)
    node_list = world.agents_by_node.get(agent.current_node, [])
    if agent_id in node_list:
        node_list.remove(agent_id)
    role_list = world.agents_by_role.get(agent.role, [])
    if agent_id in role_list:
        role_list.remove(agent_id)
    return agent


def move_agent(world: World, agent_id: str, target_node: str) -> None:
    if target_node not in world.nodes:
        raise ValueError(f"Node {target_node!r} does not exist")
    agent = world.agents[agent_id]
    old_node = agent.current_node

    node_list = world.agents_by_node.get(old_node, [])
    if agent_id in node_list:
        node_list.remove(agent_id)

    agent.current_node = target_node
    world.agents_by_node.setdefault(target_node, []).append(agent_id)


def get_node(world: World, node_id: str) -> Node:
    return world.nodes[node_id]


def agents_at(world: World, node_id: str) -> list[Agent]:
    ids = world.agents_by_node.get(node_id, [])
    return [world.agents[aid] for aid in ids]


def edges_from(world: World, node_id: str) -> list:
    return [e for e in world.edges if (e.u == node_id or e.v == node_id) and not e.severed]


def total_stock(world: World, good: str) -> int:
    """Sum of good across all node stockpiles."""
    return sum(node.stockpile.get(good, 0) for node in world.nodes.values())


def scarcity(world: World, good: str) -> float:
    """Inverse of total supply — higher means scarcer."""
    total = total_stock(world, good)
    return 1.0 / max(total, 1)
