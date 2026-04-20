"""Balancing values — good prices, weapon stats, raid parameters."""

from agent_society.schema import NeedType

# Base barter value relative to wheat = 1.0
BASE_VALUE: dict[str, float] = {
    "wheat": 1.0,
    "meat": 2.0,
    "fruit": 3.0,
    "cooked_meal": 4.0,
    "ore": 2.0,
    "plow": 8.0,
    "sickle": 6.0,
    "pickaxe": 7.0,
    "pruning_shears": 6.0,
    "cooking_tools": 4.0,
    "cart": 10.0,
    "sword": 12.0,
    "bow": 9.0,
}

WEAPON_POWER: dict[str, int] = {
    "sword": 30,   # individual fighting power — not compounded by grouping
    "bow": 20,
}

# Raid parameters
RAID_RATE: float = 0.4              # fraction of stockpile taken on successful raid
DESTRUCTION_FACTOR: float = 0.15   # fraction of loot destroyed during raid

# Raider strength changes
STRENGTH_GAIN_FROM_SUCCESS: float = 2.0
STRENGTH_LOSS_FROM_FAILURE: float = 3.0
STRENGTH_LOSS_FROM_BASE_ATTACK: float = 20.0
STRENGTH_STARVATION_DECAY: float = 1.0  # per day

# Needs decay rates per tick
DECAY_RATES: dict[NeedType, float] = {
    NeedType.HUNGER: 0.06,           # 1 tick = 1 hour; hungry in ~8 hours (3 meals/day)
    NeedType.FOOD_SATISFACTION: 0.02, # satiety lasts ~1 day (50 ticks)
    NeedType.TOOL_NEED: 0.0,         # only rises when tools wear down
    NeedType.SAFETY: 0.010,          # decays — recover in ~4 days after a raid
}

# ── Market price system ───────────────────────────────────────────────────────

# "Normal" stockpile level at a node — price equals BASE_VALUE at this level.
# Below normal → price rises; above → price falls (floor = 0.5 × BASE_VALUE).
NORMAL_STOCKPILE: dict[str, int] = {
    "wheat":        20,
    "meat":         15,
    "fruit":        10,
    "cooked_meal":  10,
    "ore":          15,
    "sword":         5,
    "plow":          4,
    "sickle":        4,
    "pickaxe":       4,
    "pruning_shears": 3,
    "cooking_tools": 3,
    "cart":          2,
    "bow":           3,
}

# Price sensitivity to scarcity.
# price = BASE_VALUE * clamp(1 + SCARCITY_K * (1 - stock/normal), 0.5, 1 + SCARCITY_K)
# SCARCITY_K = 2.0 → max price = 3× BASE_VALUE (at zero stock)
SCARCITY_K: float = 2.0

# Minimum profit margin for a merchant to bother making a trip (in gold per unit)
MERCHANT_MIN_MARGIN: float = 0.5

# Initial gold given to agents at world creation
MERCHANT_INITIAL_GOLD: int = 30
PRODUCER_INITIAL_GOLD: int = 10   # 생산자 초기 gold (도구 구매용)
NODE_INITIAL_GOLD: int = 50       # 노드 초기 gold pool (거래 유동성)

# Gold wage per unit produced (gold 발행 원점 — 노동이 가치를 창출)
PRODUCE_WAGE: float = 0.5         # BASE_VALUE × PRODUCE_WAGE = 생산 1단위당 임금

# ── Inflation & Tax ───────────────────────────────────────────────────────────
# 전체 유통 gold 합계 기준 인플레이션 배율 조정
BASELINE_GOLD: int = 800          # 이 수준에서 inflation_factor = 1.0
INFLATION_CAP: float = 3.0        # 최대 가격 배율
INFLATION_FLOOR: float = 0.5      # 최소 가격 배율

# GoldTax 이벤트 발동 임계 및 세율
GOLD_TAX_THRESHOLD: int = 2000    # total agent gold 이 수준 초과 시 세금 발동
GOLD_TAX_RATE: float = 0.20       # 보유 gold의 20% 징수

# ── Event production modifiers ────────────────────────────────────────────────

# Event production modifiers
HARVEST_BOOM_MULTIPLIER: float = 1.5
HARVEST_FAILURE_MULTIPLIER: float = 0.5
PLAGUE_PRODUCTIVITY_PENALTY: float = 0.30
