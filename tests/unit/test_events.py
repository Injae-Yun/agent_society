"""Smoke tests for WorldEventBus — FIFO, cascade depth limit."""

from __future__ import annotations

import pytest

from agent_society.events.bus import WorldEventBus
from agent_society.events.types import EventSeverity, HarvestFailure, RoadCollapse, WorldEvent
from agent_society.schema import RegionType


def _event(tick: int = 0) -> HarvestFailure:
    return HarvestFailure(
        tick=tick,
        source="test",
        severity=EventSeverity.MAJOR,
        region=RegionType.FARMLAND,
        duration=100,
    )


def test_publish_and_drain(mini_world):
    bus = WorldEventBus()
    received: list[WorldEvent] = []
    bus.subscribe(HarvestFailure, lambda e, w: received.append(e))

    ev = _event()
    bus.publish(ev)
    drained = bus.drain(mini_world)

    assert len(drained) == 1
    assert drained[0] is ev
    assert received[0] is ev


def test_fifo_order(mini_world):
    bus = WorldEventBus()
    order: list[int] = []

    def handler(e: WorldEvent, w) -> None:
        order.append(e.tick)

    bus.subscribe(HarvestFailure, handler)
    for i in range(5):
        bus.publish(_event(tick=i))

    bus.drain(mini_world)
    assert order == list(range(5))


def test_queue_empty_after_drain(mini_world):
    bus = WorldEventBus()
    bus.publish(_event())
    bus.drain(mini_world)
    # Second drain should find nothing
    result = bus.drain(mini_world)
    assert result == []


def test_unsubscribe(mini_world):
    bus = WorldEventBus()
    called = []
    sub_id = bus.subscribe(HarvestFailure, lambda e, w: called.append(1))
    bus.unsubscribe(sub_id)
    bus.publish(_event())
    bus.drain(mini_world)
    assert called == []


def test_cascade_depth_limit(mini_world):
    """Handler that keeps publishing — should stop at MAX_CASCADE_DEPTH."""
    from agent_society.config.parameters import MAX_CASCADE_DEPTH

    bus = WorldEventBus()
    publish_count = [0]

    def cascading_handler(e: WorldEvent, w) -> None:
        publish_count[0] += 1
        bus.publish(_event())  # always re-publish

    bus.subscribe(HarvestFailure, cascading_handler)
    bus.publish(_event())
    # Should not raise or loop infinitely
    bus.drain(mini_world)
    # Fired at most MAX_CASCADE_DEPTH + 1 times
    assert publish_count[0] <= MAX_CASCADE_DEPTH + 1


def test_event_is_expired():
    ev = _event(tick=0)  # duration=100
    assert not ev.is_expired(50)
    assert ev.is_expired(100)


def test_road_collapse_handler(mini_world):
    from agent_society.events.handlers import register_all_handlers

    bus = WorldEventBus()
    register_all_handlers(bus)

    collapse = RoadCollapse(
        tick=0,
        source="test",
        severity=EventSeverity.MAJOR,
        edge_u="city.market",
        edge_v="farm.hub",
    )
    bus.publish(collapse)
    bus.drain(mini_world)

    edge = mini_world.edges[0]
    assert edge.severed is True


def test_handler_exception_does_not_crash_bus(mini_world):
    bus = WorldEventBus()

    def bad_handler(e, w):
        raise RuntimeError("boom")

    bus.subscribe(HarvestFailure, bad_handler)
    bus.publish(_event())
    # Should not propagate the exception
    bus.drain(mini_world)
