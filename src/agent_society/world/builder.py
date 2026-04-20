"""World factory — builds World instances from code or YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent_society.config.balance import MERCHANT_INITIAL_GOLD, NODE_INITIAL_GOLD, PRODUCER_INITIAL_GOLD
from agent_society.schema import Agent, Edge, Item, Node, RaiderFaction, RegionType, Role, Tier, World
from agent_society.world.world import build_indices


def build_world_from_yaml(path: Path | str) -> World:
    """Load a scenario YAML and return a fully initialised World."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    nodes: dict[str, Node] = {}
    for n in data.get("nodes", []):
        node = Node(
            id=n["id"],
            name=n["name"],
            region=RegionType(n["region"]),
            stockpile=n.get("stockpile", {}),
            affordances=n.get("affordances", []),
            gold=n.get("gold", NODE_INITIAL_GOLD),
        )
        nodes[node.id] = node

    edges: list[Edge] = []
    for e in data.get("edges", []):
        edges.append(
            Edge(
                u=e["u"],
                v=e["v"],
                travel_cost=e["travel_cost"],
                base_threat=e.get("base_threat", 0.0),
                capacity=e.get("capacity", 1),
                severed=e.get("severed", False),
            )
        )

    agents: dict[str, Agent] = {}
    for a in data.get("agents", []):
        role = Role(a["role"])
        weapon_data = a.get("equipped_weapon")
        weapon: Item | None = None
        if weapon_data:
            weapon = Item(
                type=weapon_data["type"],
                tier=Tier(weapon_data.get("tier", "basic")),
                durability=weapon_data["durability"],
                max_durability=weapon_data["max_durability"],
            )

        if role == Role.RAIDER:
            agent: Agent = RaiderFaction(
                id=a["id"],
                name=a["name"],
                role=role,
                home_node=a["home_node"],
                current_node=a.get("current_node", a["home_node"]),
                inventory=a.get("inventory", {}),
                equipped_weapon=weapon,
                strength=float(a.get("strength", 30.0)),
            )
        else:
            agent = Agent(
                id=a["id"],
                name=a["name"],
                role=role,
                home_node=a["home_node"],
                current_node=a.get("current_node", a["home_node"]),
                inventory=a.get("inventory", {}),
                equipped_weapon=weapon,
                gold=a.get("gold", MERCHANT_INITIAL_GOLD if role == Role.MERCHANT else PRODUCER_INITIAL_GOLD),
            )
        agents[agent.id] = agent

    world = World(nodes=nodes, edges=edges, agents=agents, tick=0)
    build_indices(world)
    return world


def build_mvp_world() -> World:
    """Build the default MVP world from code (no YAML required)."""
    from agent_society.config.parameters import RISKY_ROUTE_COST, SAFE_ROUTE_COST

    ng = NODE_INITIAL_GOLD
    nodes: dict[str, Node] = {
        # City
        "city.market":      Node("city.market", "City Market", RegionType.CITY, affordances=["trade"], gold=ng),
        "city.smithy":      Node("city.smithy", "Smithy", RegionType.CITY, affordances=["craft_weapons", "craft_tools"], gold=ng),
        "city.kitchen":     Node("city.kitchen", "Kitchen", RegionType.CITY, affordances=["cook"], gold=ng),
        "city.residential": Node("city.residential", "Residential", RegionType.CITY, affordances=["rest"], gold=ng),
        # Farmland
        "farm.grain_field": Node("farm.grain_field", "Grain Field", RegionType.FARMLAND, affordances=["produce_wheat"], gold=ng),
        "farm.pasture":     Node("farm.pasture", "Pasture", RegionType.FARMLAND, affordances=["produce_meat"], gold=ng),
        "farm.orchard":     Node("farm.orchard", "Orchard", RegionType.FARMLAND, affordances=["produce_fruit"], gold=ng),
        "farm.mine":        Node("farm.mine", "Mine", RegionType.FARMLAND, affordances=["produce_ore"], gold=ng),
        "farm.hub":         Node("farm.hub", "Farmland Hub", RegionType.FARMLAND, affordances=["trade"], gold=ng),
        # Raider
        "raider.hideout":   Node("raider.hideout", "Raider Hideout", RegionType.RAIDER_BASE, affordances=["raider_spawn"]),
        # Route waypoints
        "route.safe_mid":   Node("route.safe_mid", "Safe Route Midpoint", RegionType.CITY),
        "route.risky_mid":  Node("route.risky_mid", "Risky Route Midpoint", RegionType.RAIDER_BASE),
    }

    edges: list[Edge] = [
        # Safe route: city ↔ farm via safe_mid
        Edge("city.market", "route.safe_mid", SAFE_ROUTE_COST // 2, base_threat=0.10, capacity=2),
        Edge("route.safe_mid", "farm.hub", SAFE_ROUTE_COST // 2, base_threat=0.10, capacity=2),
        # Risky route: city ↔ farm via raider territory
        Edge("city.market", "route.risky_mid", RISKY_ROUTE_COST // 2, base_threat=0.70, capacity=2),
        Edge("route.risky_mid", "farm.hub", RISKY_ROUTE_COST // 2, base_threat=0.70, capacity=2),
        # Raider base connection
        Edge("route.risky_mid", "raider.hideout", 5, base_threat=0.0, capacity=1),
        # City internal
        Edge("city.market", "city.smithy", 1, capacity=10),
        Edge("city.market", "city.kitchen", 1, capacity=10),
        Edge("city.market", "city.residential", 1, capacity=10),
        # Farmland internal
        Edge("farm.hub", "farm.grain_field", 2, capacity=10),
        Edge("farm.hub", "farm.pasture", 2, capacity=10),
        Edge("farm.hub", "farm.orchard", 2, capacity=10),
        Edge("farm.hub", "farm.mine", 2, capacity=10),
    ]

    agents: dict[str, Agent] = {}

    def add(a: Agent) -> None:
        agents[a.id] = a

    ig = PRODUCER_INITIAL_GOLD
    # Farmers (x3)
    for i in range(1, 4):
        add(Agent(f"farmer_{i}", f"Farmer {i}", Role.FARMER, "farm.grain_field", "farm.grain_field", gold=ig))
    # Herders (x3)
    for i in range(1, 4):
        add(Agent(f"herder_{i}", f"Herder {i}", Role.HERDER, "farm.pasture", "farm.pasture", gold=ig))
    # Miners (x3)
    for i in range(1, 4):
        add(Agent(f"miner_{i}", f"Miner {i}", Role.MINER, "farm.mine", "farm.mine", gold=ig))
    # Orchardists (x2)
    for i in range(1, 3):
        add(Agent(f"orchardist_{i}", f"Orchardist {i}", Role.ORCHARDIST, "farm.orchard", "farm.orchard", gold=ig))
    # Blacksmiths (x2)
    for i in range(1, 3):
        add(Agent(f"blacksmith_{i}", f"Blacksmith {i}", Role.BLACKSMITH, "city.smithy", "city.smithy", gold=ig))
    # Cooks (x2)
    for i in range(1, 3):
        add(Agent(f"cook_{i}", f"Cook {i}", Role.COOK, "city.kitchen", "city.kitchen", gold=ig))
    # Merchants (x2) — start with a sword and initial gold
    sword = Item("sword", Tier.BASIC, durability=40, max_durability=50)
    for i in range(1, 3):
        add(Agent(f"merchant_{i}", f"Merchant {i}", Role.MERCHANT, "city.market", "city.market",
                  inventory={"wheat": 5, "meat": 3}, equipped_weapon=sword,
                  gold=MERCHANT_INITIAL_GOLD))
    # Raider faction (x1)
    add(RaiderFaction("raiders", "Raider Band", Role.RAIDER, "raider.hideout", "raider.hideout", strength=30.0))

    world = World(nodes=nodes, edges=edges, agents=agents, tick=0)
    build_indices(world)
    return world
