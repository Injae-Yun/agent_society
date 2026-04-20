"""Generate an HTML time-machine replay file from a simulation run."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from random import Random

# Allow running as script without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_society.agents.society import AgentSociety
from agent_society.config.parameters import DEFAULT_SEED
from agent_society.events.bus import WorldEventBus
from agent_society.events.generator import EventGenerator
from agent_society.simulation.driver import SimulationDriver
from agent_society.simulation.html_renderer import render_html
from agent_society.simulation.recorder import SimulationRecorder
from agent_society.quests import QuestGenerator
from agent_society.llm.mock_backend import MockNarrator
from agent_society.world.builder import build_mvp_world, build_world_from_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Agent-Society HTML replay")
    _default_scenario = Path(__file__).parent.parent / "configs" / "mvp_scenario.yaml"
    parser.add_argument("--scenario", type=Path, default=_default_scenario,
                        help="YAML scenario (default: configs/mvp_scenario.yaml)")
    parser.add_argument("--ticks", type=int, default=2500, help="Ticks to simulate (default: 2500 ≈ 17 in-game days, 2 quest cycles)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=Path("output/replay.html"))
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    print(f"Building world…")
    world = build_world_from_yaml(args.scenario)

    rng = Random(args.seed)
    bus = WorldEventBus()
    event_gen = EventGenerator(bus=bus, rng=Random(rng.randint(0, 2**32)))
    agent_society = AgentSociety(bus=bus, rng=Random(rng.randint(0, 2**32)))
    recorder = SimulationRecorder()
    recorder.capture_meta(world)

    driver = SimulationDriver(
        world=world,
        event_gen=event_gen,
        agent_society=agent_society,
        bus=bus,
        quest_gen=QuestGenerator(MockNarrator()),
        recorder=recorder,
    )

    print(f"Simulating {args.ticks} ticks…")
    driver.run(args.ticks)
    print(driver.summary())

    print(f"Rendering HTML → {args.output}")
    render_html(recorder.to_dict(), args.output)
    print(f"Done. Open in browser: {args.output.resolve()}")


if __name__ == "__main__":
    main()
