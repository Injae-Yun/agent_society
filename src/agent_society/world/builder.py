"""World factory — builds World instances from code or YAML.

Stockpile initialisation is driven by `economy.equilibrium`: given the
final agent roster, we compute suggested city/farm inventories so prices
sit near BASE_VALUE at tick 0. YAML may specify `stockpile:` explicitly
to override any or all goods at a node.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from agent_society.economy.config import (
    CONFIG,
    MERCHANT_INITIAL_GOLD,
    NODE_INITIAL_GOLD,
    NORMAL_STOCKPILE,
    PRODUCER_INITIAL_GOLD,
)
from agent_society.economy.equilibrium import (
    apportion_stockpile,
    suggest_baseline_gold,
    suggest_initial_stockpile,
    suggest_normal_stockpile,
)
from agent_society.schema import (
    AdventurerAgent,
    Agent,
    Edge,
    Item,
    Node,
    PlayerAgent,
    RaiderFaction,
    RegionType,
    Role,
    Tier,
    World,
)
from agent_society.world import world as world_ops
from agent_society.world.world import build_indices
from agent_society.world.hex_map import (
    CLUSTER_ID,
    HEX_COORDS,
    RISKY_ROUTE_IDS,
    SAFE_ROUTE_IDS,
    VISUAL_THREAT,
)


def _hex(node_id: str) -> tuple[int | None, int | None]:
    coord = HEX_COORDS.get(node_id)
    return (coord[0], coord[1]) if coord else (None, None)


def _agent_role_counts(agents: dict[str, Agent]) -> dict[Role, int]:
    counts: Counter[Role] = Counter()
    for a in agents.values():
        counts[a.role] += 1
    return dict(counts)


def _autogenerate_stockpiles(
    nodes: dict[str, Node],
    agents: dict[str, Agent],
) -> None:
    """Fill in city/farm stockpiles from equilibrium unless YAML already set them.

    Also updates the module-level NORMAL_STOCKPILE so the pricing formula
    reflects the current population.
    """
    counts = _agent_role_counts(agents)
    if not counts:
        return

    # Re-tune globals for this population: pricing reference + inflation baseline.
    new_normal = suggest_normal_stockpile(counts)
    NORMAL_STOCKPILE.update(new_normal)
    CONFIG.baseline_gold = suggest_baseline_gold(counts)

    totals = suggest_initial_stockpile(counts)
    apportioned = apportion_stockpile(totals)

    for node_id, goods in apportioned.items():
        node = nodes.get(node_id)
        if node is None:
            continue
        for good, qty in goods.items():
            # Respect any value explicitly set by YAML / build code.
            if good not in node.stockpile:
                node.stockpile[good] = qty


def build_world_from_yaml(path: Path | str) -> World:
    """Load a scenario YAML and return a fully initialised World."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    nodes: dict[str, Node] = {}
    for n in data.get("nodes", []):
        nid = n["id"]
        q, r = _hex(nid)
        node = Node(
            id=nid,
            name=n["name"],
            region=RegionType(n["region"]),
            stockpile=dict(n.get("stockpile", {})),
            affordances=n.get("affordances", []),
            gold=n.get("gold", NODE_INITIAL_GOLD),
            hex_q=q,
            hex_r=r,
            cluster_id=CLUSTER_ID.get(nid),
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
        elif role == Role.ADVENTURER:
            agent = AdventurerAgent(
                id=a["id"],
                name=a["name"],
                role=role,
                home_node=a["home_node"],
                current_node=a.get("current_node", a["home_node"]),
                inventory=a.get("inventory", {}),
                equipped_weapon=weapon,
                gold=a.get("gold", 60),
                skill=float(a.get("skill", 50.0)),
                combat_power=float(a.get("combat_power", 20.0)),
            )
        elif role == Role.PLAYER:
            agent = PlayerAgent(
                id=a["id"],
                name=a["name"],
                role=role,
                home_node=a["home_node"],
                current_node=a.get("current_node", a["home_node"]),
                inventory=a.get("inventory", {}),
                equipped_weapon=weapon,
                gold=a.get("gold", 100),
                skill=float(a.get("skill", 70.0)),
                combat_power=float(a.get("combat_power", 30.0)),
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

    _autogenerate_stockpiles(nodes, agents)

    world = World(nodes=nodes, edges=edges, agents=agents, tick=0)
    build_indices(world)
    return world


def _make_route_nodes() -> tuple[list[Node], list[Edge]]:
    """Generate route tile nodes and their connecting edges (risky + safe)."""
    nodes: list[Node] = []
    edges: list[Edge] = []

    # Risky (상단, 4 타일)
    for i, nid in enumerate(RISKY_ROUTE_IDS):
        q, r = _hex(nid)
        nodes.append(Node(
            id=nid,
            name=f"Risky Route Tile {i + 1}",
            region=RegionType.RAIDER_BASE,
            hex_q=q,
            hex_r=r,
        ))
    prev = "city"
    for nid in RISKY_ROUTE_IDS:
        threat = VISUAL_THREAT.get(nid, 0.35)
        edges.append(Edge(prev, nid, travel_cost=1, base_threat=threat, capacity=4))
        prev = nid
    edges.append(Edge(prev, "farm", travel_cost=1, base_threat=VISUAL_THREAT.get(prev, 0.35), capacity=4))

    # Safe (하단, 10 타일)
    for i, nid in enumerate(SAFE_ROUTE_IDS):
        q, r = _hex(nid)
        nodes.append(Node(
            id=nid,
            name=f"Safe Route Tile {i + 1}",
            region=RegionType.ROUTE,
            hex_q=q,
            hex_r=r,
        ))
    prev = "city"
    for nid in SAFE_ROUTE_IDS:
        threat = VISUAL_THREAT.get(nid, 0.02)
        edges.append(Edge(prev, nid, travel_cost=1, base_threat=threat, capacity=4))
        prev = nid
    edges.append(Edge(prev, "farm", travel_cost=1, base_threat=VISUAL_THREAT.get(prev, 0.02), capacity=4))

    # Hideout adjacency — risky.3 ↔ hideout
    edges.append(Edge("route.risky.3", "raider.hideout", travel_cost=1, base_threat=0.0, capacity=1))

    return nodes, edges


def build_mvp_world() -> World:
    """Build the default MVP world from code (no YAML required)."""
    ng = NODE_INITIAL_GOLD
    nodes: dict[str, Node] = {
        "city": Node(
            "city", "City", RegionType.CITY,
            affordances=["trade", "craft_weapons", "craft_tools", "cook", "rest"],
            gold=ng, **_hc("city"), cluster_id="city",
        ),
        "farm": Node(
            "farm", "Farmland", RegionType.FARMLAND,
            affordances=["trade", "produce_wheat", "produce_meat", "produce_fruit", "produce_ore"],
            gold=ng, **_hc("farm"), cluster_id="farm",
        ),
        "raider.hideout": Node(
            "raider.hideout", "Raider Hideout", RegionType.RAIDER_BASE,
            affordances=["raider_spawn"], stockpile={"meat": 3}, **_hc("raider.hideout"),
        ),
    }

    route_nodes, route_edges = _make_route_nodes()
    for rn in route_nodes:
        nodes[rn.id] = rn

    edges: list[Edge] = route_edges

    agents: dict[str, Agent] = {}

    def add(a: Agent) -> None:
        agents[a.id] = a

    ig = PRODUCER_INITIAL_GOLD
    for i in range(1, 4):
        add(Agent(f"farmer_{i}",  f"Farmer {i}",  Role.FARMER,  "farm", "farm", gold=ig))
    for i in range(1, 4):
        add(Agent(f"herder_{i}",  f"Herder {i}",  Role.HERDER,  "farm", "farm", gold=ig))
    for i in range(1, 4):
        add(Agent(f"miner_{i}",   f"Miner {i}",   Role.MINER,   "farm", "farm", gold=ig))
    for i in range(1, 3):
        add(Agent(f"orchardist_{i}", f"Orchardist {i}", Role.ORCHARDIST, "farm", "farm", gold=ig))
    for i in range(1, 3):
        add(Agent(f"blacksmith_{i}", f"Blacksmith {i}", Role.BLACKSMITH, "city", "city", gold=ig))
    for i in range(1, 3):
        add(Agent(f"cook_{i}", f"Cook {i}", Role.COOK, "city", "city", gold=ig))
    sword = Item("sword", Tier.BASIC, durability=40, max_durability=50)
    for i in range(1, 3):
        add(Agent(f"merchant_{i}", f"Merchant {i}", Role.MERCHANT, "city", "city",
                  inventory={"wheat": 5, "meat": 3}, equipped_weapon=sword,
                  gold=MERCHANT_INITIAL_GOLD))
    add(RaiderFaction("raiders", "Raider Band", Role.RAIDER, "raider.hideout", "raider.hideout", strength=30.0))

    _autogenerate_stockpiles(nodes, agents)

    world = World(nodes=nodes, edges=edges, agents=agents, tick=0)
    build_indices(world)
    return world


def _hc(node_id: str) -> dict:
    """Return hex_q, hex_r kwargs for a node."""
    coord = HEX_COORDS.get(node_id)
    if coord:
        return {"hex_q": coord[0], "hex_r": coord[1]}
    return {}
