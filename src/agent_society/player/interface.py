"""PlayerInterface — how the outside world feeds input into the PlayerAgent.

A tick cannot block waiting for user input, so interfaces return either an
action (enqueued from a script, stdin, or network) or None (the player
passes this tick).
"""

from __future__ import annotations

from collections import deque
from typing import Protocol, TYPE_CHECKING

from agent_society.player.actions import PlayerAction

if TYPE_CHECKING:
    from agent_society.schema import PlayerAgent, World


class PlayerInterface(Protocol):
    """Source of PlayerAction objects for the per-tick loop."""

    def next_action(self, world: "World", player: "PlayerAgent") -> PlayerAction | None:
        """Return the next action to execute, or None to idle this tick."""
        ...


class IdlePlayer:
    """Default interface — the player does nothing. Useful when running NPC-only
    simulations without tearing out the PlayerAgent wiring."""

    def next_action(self, world, player):
        return None


class ScriptedPlayer:
    """Consumes a pre-built queue of PlayerActions.

    Used for tests and headless demos — the simulation drains actions in order
    until empty, then idles.
    """

    def __init__(self, actions: list[PlayerAction] | None = None) -> None:
        self._queue: deque[PlayerAction] = deque(actions or [])

    def enqueue(self, *actions: PlayerAction) -> None:
        self._queue.extend(actions)

    def next_action(self, world, player) -> PlayerAction | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def pending(self) -> int:
        return len(self._queue)
