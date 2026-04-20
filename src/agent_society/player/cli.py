"""CLI player interface — MVP headless implementation."""

from __future__ import annotations

import logging

from agent_society.schema import World

log = logging.getLogger(__name__)


class CliPlayer:
    """Minimal headless player — logs quests, accepts no input (for MVP tick loop)."""

    def __init__(self) -> None:
        self._quests: list = []

    def tick(self, world: World) -> None:
        pass  # headless — no interactive input in MVP

    def present_quests(self, quests: list) -> None:
        self._quests = quests
        for q in quests:
            log.info("Quest: %s", q)
