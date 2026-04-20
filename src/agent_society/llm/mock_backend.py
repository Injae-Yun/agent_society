"""MockNarrator — deterministic stub for tests and LLM fallback."""

from __future__ import annotations


class MockNarrator:
    """Returns a simple deterministic string — no LLM call."""

    def narrate(self, intent: object, context: object) -> str:
        quest_type = getattr(intent, "quest_type", "unknown")
        target = getattr(intent, "target", "?")
        return f"[MOCK] {quest_type} @ {target}"
