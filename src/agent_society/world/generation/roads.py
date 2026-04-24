"""Road connectivity — MST over settlement centroids + A* tile painting.

After pieces are placed, `place_roads()`:
  1. Builds a complete graph over the given settlement node ids (weight =
     hex_distance between centroids).
  2. Extracts a minimum spanning tree (Kruskal w/ union-find).
  3. Optionally adds a few extra loop edges so the graph is not strictly a
     tree — more interesting merchant routes, and a fallback when an MST
     edge gets severed by events.
  4. For each resulting graph edge, runs A* across world.tiles and paints
     RoadType.PATH (or HIGHWAY if the pair is flagged) along the hex path.
  5. Appends logical `Edge(u, v, travel_cost=…)` to world.edges so the
     existing selection / travel_planner logic has named connections.

Idempotent-ish: calling twice produces duplicate Edges but re-painting the
same tiles is harmless. Call once during world build.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_society.schema import Edge, RoadType, World
from agent_society.world.tiles import a_star, hex_distance


@dataclass
class RoadPlan:
    """Summary of a road-laying pass."""
    mst_edges: list[tuple[str, str]] = field(default_factory=list)
    loop_edges: list[tuple[str, str]] = field(default_factory=list)
    paths: dict[tuple[str, str], list[tuple[int, int]]] = field(default_factory=dict)

    @property
    def edge_count(self) -> int:
        return len(self.mst_edges) + len(self.loop_edges)


def place_roads(
    world: World,
    settlement_node_ids: list[str],
    *,
    highway_pairs: set[frozenset[str]] | None = None,
    add_loop_edges: int = 0,
    capacity: int = 4,
    skip_if_connected: bool = True,
) -> RoadPlan:
    """Connect settlements with roads over the hex-tile grid.

    Parameters
    ----------
    world
        Target world with a populated `tiles` grid and existing `nodes`.
    settlement_node_ids
        Nodes whose centroids should be connected. Order doesn't matter.
    highway_pairs
        Pairs of node ids (as `frozenset[str]`) to upgrade to HIGHWAY. Use
        for capital↔capital or other major connections.
    add_loop_edges
        Beyond MST, include this many shortest non-MST edges so merchant
        traffic has alternatives.
    capacity
        Capacity of the logical Edge records created on world.edges.
    skip_if_connected
        If an Edge(u, v) or Edge(v, u) already exists in world.edges, don't
        create a duplicate (re-paint of tiles still happens).
    """
    plan = RoadPlan()
    centers: list[tuple[str, tuple[int, int]]] = []
    for nid in settlement_node_ids:
        node = world.nodes.get(nid)
        if node is None or node.hex_q is None or node.hex_r is None:
            continue
        centers.append((nid, (node.hex_q, node.hex_r)))

    if len(centers) < 2:
        return plan

    # ── MST via Kruskal (union-find) ─────────────────────────────────────────
    pair_weights: list[tuple[int, str, str]] = []
    for i in range(len(centers)):
        a_id, a_hex = centers[i]
        for j in range(i + 1, len(centers)):
            b_id, b_hex = centers[j]
            pair_weights.append((hex_distance(a_hex, b_hex), a_id, b_id))
    pair_weights.sort()

    parent = {cid: cid for cid, _ in centers}

    def _find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]   # path compression
            x = parent[x]
        return x

    mst_set: set[frozenset[str]] = set()
    for _, a, b in pair_weights:
        ra, rb = _find(a), _find(b)
        if ra == rb:
            continue
        parent[ra] = rb
        plan.mst_edges.append((a, b))
        mst_set.add(frozenset([a, b]))
        if len(plan.mst_edges) == len(centers) - 1:
            break

    # ── Optional loop edges (next shortest non-MST pairs) ────────────────────
    if add_loop_edges > 0:
        added = 0
        for _, a, b in pair_weights:
            if added >= add_loop_edges:
                break
            if frozenset([a, b]) in mst_set:
                continue
            plan.loop_edges.append((a, b))
            added += 1

    # ── Paint tiles + register logical edges ─────────────────────────────────
    highway_pairs = highway_pairs or set()
    center_dict = dict(centers)
    existing_edges = {frozenset([e.u, e.v]) for e in world.edges}

    for (a, b) in plan.mst_edges + plan.loop_edges:
        a_hex = center_dict[a]
        b_hex = center_dict[b]
        path = a_star(world.tiles, a_hex, b_hex)
        if path is None or len(path) < 2:
            continue

        road_type = RoadType.HIGHWAY if frozenset([a, b]) in highway_pairs else RoadType.PATH
        for coord in path:
            tile = world.tiles.get(coord)
            if tile is None:
                continue
            # Only upgrade existing roads — never downgrade.
            if tile.road_type.value < road_type.value:
                tile.road_type = road_type

        if not (skip_if_connected and frozenset([a, b]) in existing_edges):
            world.edges.append(Edge(
                u=a, v=b,
                travel_cost=max(1, len(path) - 1),
                capacity=capacity,
            ))
            existing_edges.add(frozenset([a, b]))

        plan.paths[(a, b)] = path

    return plan
