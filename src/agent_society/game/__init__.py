"""Game-layer systems — dice, combat resolution, narrative hooks.

Separate from `agents/` (which is about utility-AI agent behaviour) and from
`quests/` (which is about quest lifecycle). This is where the *game feel*
lives: randomness, outcomes, the stuff an LLM narrates.
"""

from agent_society.game.dice import CheckOutcome, CheckResult, d20_check, outcome_multiplier

__all__ = ["CheckOutcome", "CheckResult", "d20_check", "outcome_multiplier"]
