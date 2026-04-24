"""Hand-stitch a small map from pieces and render to HTML.

Demonstrates the M7a piece library + placer with no procedural generation:
6 pieces are placed at hand-picked anchors, agents seeded, and the result
written to `output/demo_pieces.html`.

Run:
    python scripts/demo_pieces.py
    open output/demo_pieces.html
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_society.agents.society import AgentSociety
from agent_society.events.bus import WorldEventBus
from agent_society.events.generator import EventGenerator
from agent_society.factions import DEFAULT_FACTIONS
from agent_society.llm.mock_backend import MockNarrator
from agent_society.quests import QuestGenerator
from agent_society.schema import (
    Biome,
    Faction,
    HexTile,
    World,
)
from agent_society.simulation.driver import SimulationDriver
from agent_society.simulation.html_renderer import render_html
from agent_society.simulation.recorder import SimulationRecorder
from agent_society.schema import SettlementTier
from agent_society.world.generation import place_raider_lair, place_roads
from agent_society.world.pieces import PIECES, place_piece, seed_piece_agents
from agent_society.world.tiles import hex_within
from agent_society.world.world import build_indices


def _paint_biome(world: World, center: tuple[int, int], radius: int, biome: Biome) -> None:
    """Paint a circular patch of biome around `center`. Used to pre-condition
    anchor tiles so non-PLAINS pieces can be placed on a PLAINS-default grid."""
    for h in hex_within(center, radius):
        tile = world.tiles.get(h)
        if tile is not None:
            tile.biome = biome


def _empty_world(half: int = 8) -> World:
    """Square hex bbox of plains tiles."""
    tiles = {
        (q, r): HexTile(q=q, r=r, biome=Biome.PLAINS)
        for q in range(-half, half + 1)
        for r in range(-half, half + 1)
    }
    factions = {fid: Faction(f.id, f.name, f.home_region, f.hostile_by_default)
                for fid, f in DEFAULT_FACTIONS.items()}
    return World(nodes={}, edges=[], agents={}, tiles=tiles, factions=factions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("output/demo_pieces.html"))
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout,
    )

    rng = Random(args.seed)
    world = _empty_world()

    # Pre-paint biome patches so non-PLAINS pieces have a compatible anchor.
    _paint_biome(world, ( -2,  5), radius=2, biome=Biome.HILLS)       # mining
    _paint_biome(world, (  4,  5), radius=1, biome=Biome.FOREST)      # ruin

    # ── Hand-stitch — settlements + landmark. Raider lair placed
    #    procedurally later, after roads exist. ─────────────────────────────
    layout = [
        ("capital_civic",   ( -5,  0), "civic",   "alpha"),
        ("capital_rural",   (  5,  1), "rural",   "alpha"),
        ("village_farm",    (  1, -3), "rural",   "north"),
        ("mining_camp",     ( -2,  5), "rural",   "south"),
        ("ancient_ruin",    (  4,  5), None,      "old"),
    ]

    placements: list = []   # (piece, PlacementResult)
    for piece_id, anchor, faction, suffix in layout:
        piece = PIECES[piece_id]
        result = place_piece(
            world, piece, anchor[0], anchor[1],
            faction_id=faction, name_suffix=suffix,
        )
        if result.skipped:
            print(f"  [-] skip {piece_id}@{anchor}: {result.reason}")
            continue
        seeded = seed_piece_agents(world, result, piece, rng, faction_id=faction)
        placements.append((piece, result))
        print(f"  [+] {piece_id}@{anchor} -> node={result.node_id}, "
              f"agents={len(seeded)}")

    # Initialise hex positions for spawned agents (piece placer already set
    # current_hex for producers; this is a safety net for raider/landmark cases)
    for agent in world.agents.values():
        if agent.current_hex is None:
            node = world.nodes.get(agent.current_node)
            if node and node.hex_q is not None:
                agent.current_hex = (node.hex_q, node.hex_r)
        if agent.current_hex is not None:
            agent.known_tiles.add(agent.current_hex)

    build_indices(world)

    # ── Classify settlements for road + lair passes ──────────────────────────
    city_node_ids: list[str] = []
    village_node_ids: list[str] = []
    road_nodes: list[str] = []
    for piece, result in placements:
        if piece.is_landmark or piece.kind == "raider_lair":
            continue
        road_nodes.append(result.node_id)
        if piece.tier == SettlementTier.CAPITAL:
            city_node_ids.append(result.node_id)
        elif piece.tier in (SettlementTier.VILLAGE, SettlementTier.TOWN):
            village_node_ids.append(result.node_id)

    # Capital ↔ capital = HIGHWAY
    highway_pairs: set[frozenset[str]] = set()
    for i in range(len(city_node_ids)):
        for j in range(i + 1, len(city_node_ids)):
            highway_pairs.add(frozenset([city_node_ids[i], city_node_ids[j]]))
    plan = place_roads(
        world, road_nodes,
        highway_pairs=highway_pairs,
        add_loop_edges=1,
    )
    print(f"\nRoads: {len(plan.mst_edges)} MST + {len(plan.loop_edges)} loop "
          f"= {plan.edge_count} connections")

    # ── Raider lair — placed after roads so it can tap into one ──────────────
    lair_res = place_raider_lair(
        world, PIECES["lair_outpost"],
        village_node_ids=village_node_ids,
        city_node_ids=city_node_ids,
        rng=rng,
        name_suffix="ridge",
    )
    if lair_res.skipped:
        print(f"  [-] lair: skipped ({lair_res.skipped_reason})")
    else:
        print(f"  [+] lair_outpost@{lair_res.lair_hex} (near {lair_res.village_node_id}) "
              f"-> node={lair_res.placement.node_id}, trail={len(lair_res.road_path)} hex")

    print(f"\nWorld: {len(world.nodes)} nodes, {len(world.agents)} agents, "
          f"{len(world.tiles)} tiles, {len(world.factions)} factions")

    # ── Run a short simulation just for visual life ──────────────────────────
    bus = WorldEventBus()
    event_gen = EventGenerator(bus=bus, rng=Random(rng.randint(0, 2**32)))
    society = AgentSociety(bus=bus, rng=Random(rng.randint(0, 2**32)))
    quest_gen = QuestGenerator(MockNarrator())
    recorder = SimulationRecorder()
    recorder.capture_meta(world)

    driver = SimulationDriver(
        world=world, event_gen=event_gen, agent_society=society, bus=bus,
        quest_gen=quest_gen, recorder=recorder,
    )
    print(f"\nSimulating {args.ticks} ticks…")
    driver.run(args.ticks)

    render_html(recorder.to_dict(), args.output)
    print(f"\nHTML → {args.output.resolve()}")


if __name__ == "__main__":
    main()
