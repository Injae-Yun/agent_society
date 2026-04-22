"""QuestNarrator protocol — the single LLM call-site boundary.

Two hooks:
  * `narrate(intent, context)`            — quest generation (M2)
  * `narrate_resolution(resolution)`      — outcome narration (M5b, DnD-style)

Backends must provide both methods; Mock/HF/Ollama implementations live in
sibling modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class QuestResolution:
    """Structured input for `narrate_resolution` — what actually happened when
    the player's (or an adventurer's) quest check fired."""
    quest_type: str
    target: str
    urgency: float
    outcome: str                 # CheckOutcome.value
    roll: int                    # 1..20
    modifier: int
    dc: int
    total: int
    reward_gold: int
    effect: dict                 # whatever apply_completion returned
    actor_name: str
    actor_role: str              # "player" | "adventurer"


@runtime_checkable
class QuestNarrator(Protocol):
    def narrate(self, intent: object, context: object) -> str:
        """Convert a QuestIntent + context into a natural-language quest string."""
        ...

    def narrate_resolution(self, resolution: QuestResolution) -> str:
        """Turn a structured quest outcome into a short Korean story line."""
        ...
