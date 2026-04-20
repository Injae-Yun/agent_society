"""Event → World state mutation handlers."""

from __future__ import annotations

import logging

from agent_society.config.balance import (
    HARVEST_BOOM_MULTIPLIER,
    HARVEST_FAILURE_MULTIPLIER,
    PLAGUE_PRODUCTIVITY_PENALTY,
    STRENGTH_LOSS_FROM_BASE_ATTACK,
)
from agent_society.events.bus import WorldEventBus
from agent_society.events.types import (
    GoldTax,
    HarvestBoom,
    HarvestFailure,
    PlagueOutbreak,
    RaidAttempt,
    RaiderDecline,
    RaiderSurge,
    RoadCollapse,
    RoadRestored,
    WorldEvent,
)
from agent_society.schema import NeedType, RaiderFaction, Role, World

log = logging.getLogger(__name__)


def handle_harvest_boom(event: WorldEvent, world: World) -> None:
    assert isinstance(event, HarvestBoom)
    for agent_id in world.agents_by_role.get(Role.FARMER, []):
        agent = world.agents[agent_id]
        # Store as a modifier on the agent (checked by ProduceAction)
        agent.inventory["_productivity_mul"] = int(HARVEST_BOOM_MULTIPLIER * 100)
    for agent_id in world.agents_by_role.get(Role.HERDER, []):
        world.agents[agent_id].inventory["_productivity_mul"] = int(HARVEST_BOOM_MULTIPLIER * 100)


def handle_harvest_failure(event: WorldEvent, world: World) -> None:
    assert isinstance(event, HarvestFailure)
    for role in (Role.FARMER, Role.HERDER, Role.ORCHARDIST):
        for agent_id in world.agents_by_role.get(role, []):
            world.agents[agent_id].inventory["_productivity_mul"] = int(HARVEST_FAILURE_MULTIPLIER * 100)


def handle_plague_outbreak(event: WorldEvent, world: World) -> None:
    assert isinstance(event, PlagueOutbreak)
    node_agents = world.agents_by_node.get(event.node, [])
    for agent_id in node_agents:
        world.agents[agent_id].inventory["_plague_penalty"] = int(PLAGUE_PRODUCTIVITY_PENALTY * 100)


def handle_road_collapse(event: WorldEvent, world: World) -> None:
    assert isinstance(event, RoadCollapse)
    for edge in world.edges:
        if (edge.u == event.edge_u and edge.v == event.edge_v) or \
           (edge.u == event.edge_v and edge.v == event.edge_u):
            edge.severed = True
            log.info("Edge %s↔%s severed", event.edge_u, event.edge_v)
            return


def handle_road_restored(event: WorldEvent, world: World) -> None:
    assert isinstance(event, RoadRestored)
    for edge in world.edges:
        if (edge.u == event.edge_u and edge.v == event.edge_v) or \
           (edge.u == event.edge_v and edge.v == event.edge_u):
            edge.severed = False
            log.info("Edge %s↔%s restored", event.edge_u, event.edge_v)
            return


def handle_raider_surge(event: WorldEvent, world: World) -> None:
    assert isinstance(event, RaiderSurge)
    for agent_id in world.agents_by_role.get(Role.RAIDER, []):
        agent = world.agents[agent_id]
        if isinstance(agent, RaiderFaction):
            agent.strength = min(100.0, agent.strength + event.delta_strength)


def handle_raider_decline(event: WorldEvent, world: World) -> None:
    assert isinstance(event, RaiderDecline)
    for agent_id in world.agents_by_role.get(Role.RAIDER, []):
        agent = world.agents[agent_id]
        if isinstance(agent, RaiderFaction):
            agent.strength = max(0.0, agent.strength - event.delta_strength)


def handle_raid_attempt(event: WorldEvent, world: World) -> None:
    assert isinstance(event, RaidAttempt)
    if event.result in ("partial_loss", "plundered"):
        # Raise safety need for all agents at target node
        for agent_id in world.agents_by_node.get(event.target_node, []):
            agent = world.agents[agent_id]
            agent.needs[NeedType.SAFETY] = min(1.0, agent.needs.get(NeedType.SAFETY, 0.0) + 0.5)
        # Raise safety for all merchants (news spreads)
        for agent_id in world.agents_by_role.get(Role.MERCHANT, []):
            agent = world.agents[agent_id]
            agent.needs[NeedType.SAFETY] = min(1.0, agent.needs.get(NeedType.SAFETY, 0.0) + 0.3)


def handle_gold_tax(event: WorldEvent, world: World) -> None:
    assert isinstance(event, GoldTax)
    total_collected = 0
    for agent in world.agents.values():
        levy = int(agent.gold * event.tax_rate)
        agent.gold -= levy
        total_collected += levy
    log.info("GoldTax: collected %dg total (rate=%.0f%%)", total_collected, event.tax_rate * 100)


def register_all_handlers(bus: WorldEventBus) -> None:
    bus.subscribe(HarvestBoom, handle_harvest_boom)
    bus.subscribe(HarvestFailure, handle_harvest_failure)
    bus.subscribe(PlagueOutbreak, handle_plague_outbreak)
    bus.subscribe(RoadCollapse, handle_road_collapse)
    bus.subscribe(RoadRestored, handle_road_restored)
    bus.subscribe(RaiderSurge, handle_raider_surge)
    bus.subscribe(RaiderDecline, handle_raider_decline)
    bus.subscribe(RaidAttempt, handle_raid_attempt)
    bus.subscribe(GoldTax, handle_gold_tax)
