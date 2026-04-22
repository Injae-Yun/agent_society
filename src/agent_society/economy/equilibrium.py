"""Equilibrium solver — maps agent population to sensible stockpile / price targets.

Instead of hand-tuning `configs/*.yaml` every time the population changes, we
derive normative values from the per-role flow model in `flows.py`:

  agent_counts ──▶ total_production / consumption / food_demand
               └─▶ suggest_normal_stockpile()   ← sets the pricing reference
               └─▶ suggest_initial_stockpile()  ← sets world-start quantities

`diagnose(world)` gives a quick read on whether the running simulation is
anywhere near the modelled equilibrium.
"""

from __future__ import annotations

from collections import Counter

from agent_society.config.parameters import TICK_PER_DAY
from agent_society.economy.config import BASE_VALUE, CONFIG
from agent_society.economy.flows import (
    net_flow,
    total_food_consumption,
    total_production,
    total_raw_consumption,
)
from agent_society.schema import Role, World


def count_agents(world: World) -> dict[Role, int]:
    """Group agents by role."""
    counts: Counter[Role] = Counter()
    for a in world.agents.values():
        counts[a.role] += 1
    return dict(counts)


# ── Normative stockpile levels ────────────────────────────────────────────────

def suggest_normal_stockpile(
    agent_counts: dict[Role, int],
    reference_days: float = 1.0,
) -> dict[str, int]:
    """NORMAL_STOCKPILE values — price == BASE_VALUE when stock sits here.

    Sized as `reference_days` worth of aggregate consumption (or production
    for goods nobody consumes, to keep producer-only items priced sanely).
    """
    ticks = max(1, int(reference_days * TICK_PER_DAY))
    raw = total_raw_consumption(agent_counts)
    food = total_food_consumption(agent_counts)
    prod = total_production(agent_counts)

    normal: dict[str, int] = {}
    for good in set(raw) | set(food) | set(prod) | set(BASE_VALUE):
        demand = raw.get(good, 0.0) + food.get(good, 0.0)
        supply = prod.get(good, 0.0)
        ref = demand if demand > 0 else supply
        normal[good] = max(3, int(round(ref * ticks)))
    return normal


def suggest_stockpile_cap(good: str, normal: int) -> int:
    """Producer-activity cap — production stops when stockpile ≥ cap.

    Sized at ~2.5× NORMAL so surplus goods still clear through merchants
    before producers idle.
    """
    return max(20, int(round(normal * 2.5)))


def suggest_stockpile_caps(agent_counts: dict[Role, int]) -> dict[str, int]:
    """Per-good producer cap derived from normal stockpile."""
    normal = suggest_normal_stockpile(agent_counts)
    return {good: suggest_stockpile_cap(good, n) for good, n in normal.items()}


def suggest_initial_stockpile(
    agent_counts: dict[Role, int],
    buffer_days: float = 5.0,
) -> dict[str, int]:
    """Initial stockpile per good — prices sit near BASE_VALUE, producers still active.

    Strategy:
      * Surplus goods: start at 0.9× NORMAL so cap headroom remains for producer
        wages at tick 0.
      * Deficit goods: 1.0× NORMAL + `buffer_days` of deficit, clamped below
        the per-good cap so producers can still fire ProduceAction on day 1.
    """
    normal = suggest_normal_stockpile(agent_counts, reference_days=1.0)
    flows = net_flow(agent_counts)
    buffer_ticks = buffer_days * TICK_PER_DAY

    stockpile: dict[str, int] = {}
    for good, n in normal.items():
        net = flows.get(good, 0.0)
        cap = suggest_stockpile_cap(good, n)
        if net >= 0:
            qty = int(round(n * 0.9))
        else:
            deficit = abs(net)
            qty = int(round(n + deficit * buffer_ticks))
        stockpile[good] = max(5, min(qty, cap - 1))
    return stockpile


def suggest_baseline_gold(agent_counts: dict[Role, int]) -> int:
    """Inflation reference — target total agent gold when prices ≈ BASE_VALUE.

    Scales with population: ~30g per non-merchant + ~100g per merchant.
    """
    non_merchant = sum(n for r, n in agent_counts.items() if r != Role.MERCHANT)
    merchants = agent_counts.get(Role.MERCHANT, 0)
    return max(200, non_merchant * 30 + merchants * 100)


# ── Apportioning stockpile to nodes ───────────────────────────────────────────

# Which node should initially hold which good. Roughly: farm holds raw farm
# output + tools used by farm producers; city holds crafted goods + meats
# going through the kitchen.
_NODE_APPORTIONMENT: dict[str, dict[str, float]] = {
    # good → {node: share (must sum to 1.0)}
    # City share is sized to keep cook crafting (needs wheat+meat) and
    # blacksmith crafting (needs ore) running without waiting on merchants.
    "wheat":          {"farm": 0.5, "city": 0.5},
    "meat":           {"farm": 0.5, "city": 0.5},
    "fruit":          {"farm": 0.7, "city": 0.3},
    "ore":            {"farm": 0.3, "city": 0.7},
    "cooked_meal":    {"city": 1.0},
    "plow":           {"farm": 0.8, "city": 0.2},
    "sickle":         {"farm": 0.8, "city": 0.2},
    "pickaxe":        {"farm": 0.8, "city": 0.2},
    "pruning_shears": {"farm": 0.8, "city": 0.2},
    "cooking_tools":  {"city": 1.0},
    "sword":          {"city": 1.0},
    "bow":            {"city": 1.0},
    "cart":           {"city": 1.0},
}


def apportion_stockpile(
    total: dict[str, int],
) -> dict[str, dict[str, int]]:
    """Split a total stockpile across city/farm according to role-ownership conventions."""
    out: dict[str, dict[str, int]] = {"city": {}, "farm": {}}
    for good, qty in total.items():
        shares = _NODE_APPORTIONMENT.get(good, {"city": 0.5, "farm": 0.5})
        for node, share in shares.items():
            amount = int(round(qty * share))
            if amount > 0:
                out.setdefault(node, {})[good] = amount
    return out


# ── Diagnostics ───────────────────────────────────────────────────────────────

def diagnose(world: World) -> dict:
    """Current economic snapshot vs. modelled equilibrium."""
    counts = count_agents(world)
    flows = net_flow(counts)
    normal = suggest_normal_stockpile(counts)

    total_agent_gold = sum(a.gold for a in world.agents.values())
    total_node_gold = sum(n.gold for n in world.nodes.values())

    stock_actual: dict[str, int] = {}
    for n in world.nodes.values():
        for good, qty in n.stockpile.items():
            if good.startswith("_"):
                continue
            stock_actual[good] = stock_actual.get(good, 0) + qty

    stock_ratio = {
        good: round(stock_actual.get(good, 0) / max(1, normal.get(good, 1)), 2)
        for good in sorted(normal)
    }

    inflation_raw = total_agent_gold / CONFIG.baseline_gold
    inflation = max(CONFIG.inflation_floor, min(CONFIG.inflation_cap, inflation_raw))

    return {
        "agent_counts":       {r.value: n for r, n in counts.items()},
        "net_flow_per_tick":  {k: round(v, 3) for k, v in sorted(flows.items())},
        "normal_stockpile":   normal,
        "actual_stockpile":   stock_actual,
        "stock_ratio":        stock_ratio,   # actual / normal — around 1.0 = priced near BASE
        "total_agent_gold":   total_agent_gold,
        "total_node_gold":    total_node_gold,
        "inflation_factor":   round(inflation, 2),
    }


def format_diagnosis(world: World) -> str:
    """Human-readable one-shot economy report."""
    d = diagnose(world)
    lines = [
        f"=== Economy @ tick {world.tick} ===",
        f"Agents: {d['agent_counts']}",
        f"Total gold: agents={d['total_agent_gold']} nodes={d['total_node_gold']}"
        f" | inflation={d['inflation_factor']}×",
        "",
        f"{'good':<16}{'flow/t':>10}{'actual':>10}{'normal':>10}{'ratio':>8}",
    ]
    for good, normal in sorted(d['normal_stockpile'].items()):
        flow = d['net_flow_per_tick'].get(good, 0.0)
        actual = d['actual_stockpile'].get(good, 0)
        ratio = d['stock_ratio'].get(good, 0.0)
        lines.append(f"{good:<16}{flow:>+10.3f}{actual:>10d}{normal:>10d}{ratio:>8.2f}")
    return "\n".join(lines)
