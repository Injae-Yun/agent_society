"""PlayerInterface protocol."""

from __future__ import annotations

from typing import Protocol

from agent_society.schema import World


class PlayerInterface(Protocol):
    def tick(self, world: World) -> None:
        """Process player input and publish resulting events."""
        ...

    def present_quests(self, quests: list) -> None:
        """Display available quests to the player."""
        ...
