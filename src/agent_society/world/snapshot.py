"""Read-only view of World state passed to systems during tick."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_society.schema import Agent, Edge, Node, RegionType, Role, World
from agent_society.world import world as world_ops

if TYPE_CHECKING:
    pass


class WorldSnapshot:
    """Proxy over World that exposes only read operations.

    Systems receive this during their tick and must not mutate world state
    directly — mutations happen through each system's own methods.
    """

    def __init__(self, world: World) -> None:
        self._world = world

    @property
    def tick(self) -> int:
        return self._world.tick

    def get_node(self, node_id: str) -> Node:
        return world_ops.get_node(self._world, node_id)

    def get_agent(self, agent_id: str) -> Agent:
        return self._world.agents[agent_id]

    def agents_at(self, node_id: str) -> list[Agent]:
        return world_ops.agents_at(self._world, node_id)

    def agents_by_role(self, role: Role) -> list[Agent]:
        ids = self._world.agents_by_role.get(role, [])
        return [self._world.agents[aid] for aid in ids]

    def edges_from(self, node_id: str) -> list[Edge]:
        return world_ops.edges_from(self._world, node_id)

    def scarcity(self, good: str) -> float:
        return world_ops.scarcity(self._world, good)

    def total_stock(self, good: str) -> int:
        return world_ops.total_stock(self._world, good)

    def all_agents(self) -> list[Agent]:
        return list(self._world.agents.values())

    def agents_in_region(self, region: RegionType) -> list[Agent]:
        """All agents currently at any node in the given region."""
        return [
            a for a in self._world.agents.values()
            if self._world.nodes.get(a.current_node, None) is not None
            and self._world.nodes[a.current_node].region == region
        ]

    def agents_within_1_hop(self, node_id: str) -> list[Agent]:
        """Agents at this node plus agents at every directly adjacent node."""
        result = list(world_ops.agents_at(self._world, node_id))
        for edge in world_ops.edges_from(self._world, node_id):
            neighbor = edge.v if edge.u == node_id else edge.u
            result.extend(world_ops.agents_at(self._world, neighbor))
        return result

    def node_ids(self) -> list[str]:
        return list(self._world.nodes.keys())

    # Prevent accidental attribute writes
    def __setattr__(self, name: str, value: object) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            raise AttributeError("WorldSnapshot is read-only")
