"""CLI entry point: python -m agent_society"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from random import Random

from agent_society.agents.society import AgentSociety
from agent_society.config.parameters import DEFAULT_SEED
from agent_society.events.bus import WorldEventBus
from agent_society.events.generator import EventGenerator
from agent_society.simulation.driver import SimulationDriver
from agent_society.world.builder import build_mvp_world, build_world_from_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent-Society simulation")
    parser.add_argument("--scenario", type=Path, help="Path to scenario YAML (default: built-in MVP)")
    parser.add_argument("--ticks", type=int, default=2500, help="Number of ticks to run (default: 2500 ≈ 17 in-game days)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    world = build_world_from_yaml(args.scenario) if args.scenario else build_mvp_world()

    rng = Random(args.seed)
    bus = WorldEventBus()
    event_gen = EventGenerator(bus=bus, rng=Random(rng.randint(0, 2**32)))
    agent_society = AgentSociety(bus=bus, rng=Random(rng.randint(0, 2**32)))

    driver = SimulationDriver(
        world=world,
        event_gen=event_gen,
        agent_society=agent_society,
        bus=bus,
    )

    driver.run(args.ticks)
    print(driver.summary())


if __name__ == "__main__":
    main()
