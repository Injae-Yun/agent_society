"""Tick ↔ in-game time conversions."""

from __future__ import annotations

from agent_society.config.parameters import TICK_PER_DAY, TICK_PER_SEASON

SEASON_NAMES = ("Spring", "Summer", "Autumn", "Winter")


def tick_to_day(tick: int) -> int:
    return tick // TICK_PER_DAY


def tick_to_season_index(tick: int) -> int:
    return (tick // TICK_PER_SEASON) % 4


def tick_to_season(tick: int) -> str:
    return SEASON_NAMES[tick_to_season_index(tick)]


def is_new_day(tick: int) -> bool:
    return tick % TICK_PER_DAY == 0


def format_time(tick: int) -> str:
    day = tick_to_day(tick)
    season = tick_to_season(tick)
    return f"Day {day} ({season})"
