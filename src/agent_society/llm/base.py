"""QuestNarrator protocol — the single LLM call-site boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class QuestNarrator(Protocol):
    def narrate(self, intent: object, context: object) -> str:
        """Convert a QuestIntent + context into a natural-language quest string."""
        ...
