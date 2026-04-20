"""Headless simulation runner."""

from __future__ import annotations

from random import Random

from agent_society.agents.society import AgentSociety
from agent_society.events.bus import WorldEventBus
from agent_society.events.generator import EventGenerator
from agent_society.simulation.driver import SimulationDriver
from agent_society.world.builder import build_mvp_world


def main(n_ticks: int = 1000, seed: int = 42) -> None:
    rng = Random(seed)
    world = build_mvp_world()
    bus = WorldEventBus()
    event_gen = EventGenerator(bus=bus, rng=Random(rng.randint(0, 2**32)))
    agent_society = AgentSociety(bus=bus, rng=Random(rng.randint(0, 2**32)))

    driver = SimulationDriver(world=world, event_gen=event_gen, agent_society=agent_society, bus=bus)
    driver.run(n_ticks)
    print(driver.summary())


if __name__ == "__main__":
    main()
