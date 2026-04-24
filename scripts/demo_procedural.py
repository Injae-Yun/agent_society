"""End-to-end procedural map demo (M7 integration).

Drives `generate_world(GenerationParams)` and runs a short simulation on
the resulting world — all settlements, roads, lair, territory, and biomes
are produced by the generator, no hand-authored YAML scenario.

    python scripts/demo_procedural.py --seed 42 --ticks 400
    open output/demo_procedural.html
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
from agent_society.llm.mock_backend import MockNarrator
from agent_society.quests import QuestGenerator
from agent_society.simulation.driver import SimulationDriver
from agent_society.simulation.html_renderer import render_html
from agent_society.simulation.recorder import SimulationRecorder
from agent_society.world.generation import GenerationParams, generate_world


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=400)
    parser.add_argument("--half", type=int, default=8, help="map half-size (hex)")
    parser.add_argument("--output", type=Path, default=Path("output/demo_procedural.html"))
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout,
    )

    params = GenerationParams(seed=args.seed, map_half_size=args.half)
    world, report = generate_world(params)

    # Summary
    print(f"seed={args.seed}  map={2*args.half+1}x{2*args.half+1}")
    print(f"settlements: {len(report.placements)}")
    for piece, placement in report.placements:
        print(f"  [+] {piece.id:16s} node={placement.node_id}")
    if report.road_plan:
        print(f"roads: {report.road_plan.edge_count} "
              f"(MST {len(report.road_plan.mst_edges)}, loops {len(report.road_plan.loop_edges)})")
    if report.lair and not report.lair.skipped:
        print(f"lair: node={report.lair.placement.node_id}@{report.lair.lair_hex} "
              f"near {report.lair.village_node_id}")
    print("biome tally:")
    for biome, count in sorted(report.biome_tally.items(), key=lambda kv: -kv[1]):
        print(f"  {biome.value:10s} {count:4d}")

    # Simulate
    rng = Random(args.seed)
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
    print(f"\nsimulating {args.ticks} ticks...")
    driver.run(args.ticks)

    render_html(recorder.to_dict(), args.output)
    print(f"\nHTML -> {args.output.resolve()}")


if __name__ == "__main__":
    main()
