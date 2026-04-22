"""PlayerAction — a single input from the player interface for one tick.

The Player goes through `tick_player()` in `agents/player.py` which dispatches
each action type to the appropriate world-mutation. Actions are produced by
`PlayerInterface.next_action()` — e.g. a script, a CLI, or eventually a GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlayerActionType(Enum):
    MOVE           = "move"
    BUY            = "buy"
    SELL           = "sell"
    CONSUME        = "consume"         # eat at current node
    FIGHT          = "fight"           # attack raider at current node
    REST           = "rest"            # recuperate 1 tick
    ACCEPT_QUEST   = "accept_quest"
    WORK_QUEST     = "work_quest"      # advance active quest progress
    COMPLETE_QUEST = "complete_quest"  # claim completion when progress ≥ 1.0


@dataclass
class PlayerAction:
    type: PlayerActionType
    target_node: str | None = None
    good: str | None = None
    qty: int | None = None
    quest_id: str | None = None
