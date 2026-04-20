"""Simulation constants — tick timing, intervals, system limits."""

TICK_PER_DAY: int = 24           # 1 hour per tick → 24 ticks = 1 in-game day
TICK_PER_SEASON: int = TICK_PER_DAY * 30  # 30 in-game days per season
TICK_PER_YEAR: int = TICK_PER_SEASON * 4

QUEST_REFRESH_INTERVAL: int = 7 * TICK_PER_DAY   # 7 in-game days between quest refreshes
MAX_CASCADE_DEPTH: int = 3          # max event cascade depth in bus.drain()
DEFAULT_SEED: int = 42

# Route travel costs (ticks)
SAFE_ROUTE_COST: int = 30
RISKY_ROUTE_COST: int = 10

# Route threat levels
SAFE_ROUTE_THREAT: float = 0.10
RISKY_ROUTE_THREAT: float = 0.70

# Route capacity
ROUTE_CAPACITY: int = 2

# Needs
URGENCY_THRESHOLD: float = 0.7     # needs value above which QuestGenerator activates
