"""WorldEventBus — pub/sub broker for WorldEvents."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Type

from agent_society.config.parameters import MAX_CASCADE_DEPTH
from agent_society.events.types import WorldEvent
from agent_society.schema import World

log = logging.getLogger(__name__)

SubscriptionId = int
Handler = Callable[[WorldEvent, World], None]


class _Subscription:
    def __init__(self, sub_id: SubscriptionId, event_type: Type[WorldEvent], handler: Handler, priority: int) -> None:
        self.sub_id = sub_id
        self.event_type = event_type
        self.handler = handler
        self.priority = priority


class WorldEventBus:
    def __init__(self) -> None:
        self._queue: list[WorldEvent] = []
        self._subs: dict[Type[WorldEvent], list[_Subscription]] = defaultdict(list)
        self._next_id: SubscriptionId = 0

    def publish(self, event: WorldEvent) -> None:
        self._queue.append(event)

    def subscribe(
        self,
        event_type: Type[WorldEvent],
        handler: Handler,
        priority: int = 0,
    ) -> SubscriptionId:
        sub_id = self._next_id
        self._next_id += 1
        sub = _Subscription(sub_id, event_type, handler, priority)
        self._subs[event_type].append(sub)
        self._subs[event_type].sort(key=lambda s: s.priority)
        return sub_id

    def unsubscribe(self, sub_id: SubscriptionId) -> None:
        for subs in self._subs.values():
            for sub in list(subs):
                if sub.sub_id == sub_id:
                    subs.remove(sub)
                    return

    def drain(self, world: World, _depth: int = 0) -> list[WorldEvent]:
        """Dispatch all queued events to subscribers; handle cascades up to MAX_CASCADE_DEPTH."""
        if not self._queue:
            return []

        if _depth >= MAX_CASCADE_DEPTH:
            log.warning("Event cascade depth %d reached limit — discarding %d events", _depth, len(self._queue))
            self._queue.clear()
            return []

        # Snapshot the current queue and clear before dispatching (cascade safety)
        current_batch = self._queue[:]
        self._queue.clear()

        for event in current_batch:
            self._dispatch(event, world)

        # Recurse for any cascade events published during dispatch
        cascade = self.drain(world, _depth + 1)
        return current_batch + cascade

    def _dispatch(self, event: WorldEvent, world: World) -> None:
        # Walk the MRO so subclass events match parent subscriptions too
        for cls in type(event).__mro__:
            if cls not in self._subs:
                continue
            for sub in self._subs[cls]:
                try:
                    sub.handler(event, world)
                except Exception:
                    log.exception("Handler %s raised on event %s — skipping", sub.handler, event)
