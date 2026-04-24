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
from agent_society.factions import DEFAULT_FACTIONS, role_to_faction
from agent_society.schema import (
    AdventurerAgent,
    Agent,
    Biome,
    Edge,
    Faction,
    HexTile,
    Item,
    Node,
    PlayerAgent,
    RaiderFaction,
    RegionType,
    RoadType,
    Role,
    Tier,
    World,
)
from agent_society.world import world as world_ops
from agent_society.world.world import build_indices
from agent_society.world.hex_map import (
    CITY_ZONE_HEXES,
    CLUSTER_HEXES,
    CLUSTER_ID,
    FARM_ZONE_HEXES,
    GATE_HEXES,
    HEX_COORDS,
    HIDEOUT_TERRITORY,
    RISKY_ROUTE_IDS,
    SAFE_ROUTE_IDS,
    VISUAL_THREAT,
)


def _hex(node_id: str) -> tuple[int | None, int | None]:
    coord = HEX_COORDS.get(node_id)
    return (coord[0], coord[1]) if coord else (None, None)


# ── M7 — dense hex-tile grid ──────────────────────────────────────────────────

def _generate_tile_grid(
    nodes: dict[str, Node],
    padding: int = 4,
) -> dict[tuple[int, int], HexTile]:
    """Build a rectangular hex-coord grid covering every named node plus padding.

    Biome assignment for the hand-authored MVP map:
      * URBAN:     city/farm zone hexes
      * WASTELAND: hideout territory
      * route tiles get a `road_type=PATH` overlay (biome stays PLAINS)
      * everything else: PLAINS default
    """
    coords = [
        (n.hex_q, n.hex_r) for n in nodes.values()
        if n.hex_q is not None and n.hex_r is not None
    ]
    if not coords:
        return {}

    min_q = min(q for q, _ in coords) - padding
    max_q = max(q for q, _ in coords) + padding
    min_r = min(r for _, r in coords) - padding
    max_r = max(r for _, r in coords) + padding

    urban = {tuple(h) for hex_list in CLUSTER_HEXES.values() for h in hex_list}
    wasteland = {tuple(h) for h in HIDEOUT_TERRITORY}

    route_coords: set[tuple[int, int]] = set()
    route_ids = set(SAFE_ROUTE_IDS) | set(RISKY_ROUTE_IDS)
    for nid in route_ids:
        node = nodes.get(nid)
        if node is None or node.hex_q is None:
            continue
        route_coords.add((node.hex_q, node.hex_r))

    tiles: dict[tuple[int, int], HexTile] = {}
    for q in range(min_q, max_q + 1):
        for r in range(min_r, max_r + 1):
            coord = (q, r)
            biome = Biome.PLAINS
            road = RoadType.NONE
            if coord in urban:
                biome = Biome.URBAN
            elif coord in wasteland:
                biome = Biome.WASTELAND
            if coord in route_coords:
                road = RoadType.PATH      # paint path on existing biome
            if coord in GATE_HEXES:
                # Zone gate — PATH overlay makes A* prefer this hex over
                # the adjacent producer slot when leaving/entering a zone.
                road = RoadType.PATH
            tiles[coord] = HexTile(q=q, r=r, biome=biome, road_type=road)

    # Overlay node_id on the hex a named Node sits on.
    for nid, node in nodes.items():
        if node.hex_q is None or node.hex_r is None:
            continue
        tile = tiles.get((node.hex_q, node.hex_r))
        if tile is not None:
            tile.node_id = nid

    return tiles


def _init_agent_hex(agents: dict[str, Agent], nodes: dict[str, Node]) -> None:
    """Seed each agent's hex position from their current_node, preferring the
    role-specific visual slot from hex_map.ROLE_VISUAL_OFFSET when available
    (so the legacy mvp_scenario keeps its smithy/kitchen/grain layout)."""
    from agent_society.world.hex_map import ROLE_VISUAL_OFFSET
    for agent in agents.values():
        node = nodes.get(agent.current_node)
        if node is None or node.hex_q is None or node.hex_r is None:
            continue
        slot = ROLE_VISUAL_OFFSET.get((agent.current_node, agent.role.value))
        agent.current_hex = slot if slot is not None else (node.hex_q, node.hex_r)
        # Known-tiles seed — the agent can always see their starting hex.
        agent.known_tiles.add(agent.current_hex)


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

    # Factions — yaml override if present, else defaults.
    factions = _load_factions(data.get("factions"))
    # Assign faction_id to each agent based on yaml override or role default.
    _assign_factions(agents, data.get("agents", []), factions)

    # M7 — hex tile grid + agent hex seed
    tiles = _generate_tile_grid(nodes)
    _init_agent_hex(agents, nodes)

    world = World(
        nodes=nodes, edges=edges, agents=agents, tick=0,
        factions=factions, tiles=tiles,
    )
    build_indices(world)
    return world


def _load_factions(yaml_factions: list[dict] | None) -> dict[str, Faction]:
    """yaml override or DEFAULT_FACTIONS copy."""
    if not yaml_factions:
        return {fid: Faction(f.id, f.name, f.home_region, f.hostile_by_default)
                for fid, f in DEFAULT_FACTIONS.items()}
    out: dict[str, Faction] = {}
    for entry in yaml_factions:
        fid = entry["id"]
        out[fid] = Faction(
            id=fid,
            name=entry.get("name", fid.title()),
            home_region=entry.get("home_region", ""),
            hostile_by_default=bool(entry.get("hostile_by_default", False)),
        )
    return out


def _assign_factions(
    agents: dict[str, Agent],
    yaml_agents: list[dict],
    factions: dict[str, Faction],
) -> None:
    """For each agent, pick yaml-specified faction_id or fall back to role map."""
    yaml_map = {a["id"]: a.get("faction_id") for a in yaml_agents}
    for aid, agent in agents.items():
        fid = yaml_map.get(aid) or role_to_faction(agent.role)
        if fid is not None and fid in factions:
            agent.faction_id = fid


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

    # Factions default set + role-based assignment
    factions = {fid: Faction(f.id, f.name, f.home_region, f.hostile_by_default)
                for fid, f in DEFAULT_FACTIONS.items()}
    for agent in agents.values():
        fid = role_to_faction(agent.role)
        if fid is not None and fid in factions:
            agent.faction_id = fid

    tiles = _generate_tile_grid(nodes)
    _init_agent_hex(agents, nodes)

    world = World(
        nodes=nodes, edges=edges, agents=agents, tick=0,
        factions=factions, tiles=tiles,
    )
    build_indices(world)
    return world


def _hc(node_id: str) -> dict:
    """Return hex_q, hex_r kwargs for a node."""
    coord = HEX_COORDS.get(node_id)
    if coord:
        return {"hex_q": coord[0], "hex_r": coord[1]}
    return {}
