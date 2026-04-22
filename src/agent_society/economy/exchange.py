"""Market price calculation + barter exchange rate."""

from __future__ import annotations

from agent_society.economy.config import BASE_VALUE, CONFIG, NORMAL_STOCKPILE
from agent_society.economy.goods import base_value


def inflation_factor(total_gold: int) -> float:
    """유통 gold 총량 기반 인플레이션 배율 (1.0 = 기준).

    Reads CONFIG at call-time so builder-time re-tuning of `baseline_gold`
    (e.g. scaling with agent count) takes effect immediately.
    """
    raw = total_gold / max(CONFIG.baseline_gold, 1)
    return max(CONFIG.inflation_floor, min(CONFIG.inflation_cap, raw))


# ── Gold-based market price ───────────────────────────────────────────────────

def node_price(stockpile: dict[str, int], good: str, total_gold: int = 0) -> float:
    """현재 node stockpile 기준 재화 1단위의 gold 가격.

    stockpile == NORMAL_STOCKPILE → price == BASE_VALUE
    stockpile == 0                → price == BASE_VALUE * (1 + SCARCITY_K)
    stockpile >> NORMAL           → price → BASE_VALUE * 0.5 (하한)
    """
    base = BASE_VALUE.get(good, 1.0)
    normal = NORMAL_STOCKPILE.get(good, 10)
    stock = max(0, stockpile.get(good, 0))
    ratio = stock / normal if normal > 0 else 1.0
    scarcity = base * (1.0 + CONFIG.scarcity_k * (1.0 - ratio))
    floor = base * 0.5
    ceiling = base * (1.0 + CONFIG.scarcity_k)
    price = max(floor, min(ceiling, scarcity))
    if total_gold > 0:
        price *= inflation_factor(total_gold)
    return round(price, 2)


def best_buy_opportunity(
    world_nodes: dict,          # {node_id: Node}
    good: str,
    exclude_node: str | None = None,
) -> tuple[str, float] | None:
    """전체 노드 중 해당 재화의 최저가 노드와 가격 반환."""
    best: tuple[str, float] | None = None
    for nid, node in world_nodes.items():
        if nid == exclude_node:
            continue
        p = node_price(node.stockpile, good)
        if best is None or p < best[1]:
            best = (nid, p)
    return best


def best_sell_opportunity(
    world_nodes: dict,          # {node_id: Node}
    good: str,
    exclude_node: str | None = None,
) -> tuple[str, float] | None:
    """전체 노드 중 해당 재화의 최고가 노드와 가격 반환."""
    best: tuple[str, float] | None = None
    for nid, node in world_nodes.items():
        if nid == exclude_node:
            continue
        p = node_price(node.stockpile, good)
        if best is None or p > best[1]:
            best = (nid, p)
    return best


# ── Barter exchange rate (NPC간 물물교환용, 기존 유지) ───────────────────────

def exchange_rate(item_a: str, item_b: str, world_stock: dict[str, int]) -> float:
    """item_a 1단위 교환에 필요한 item_b 단위 수."""
    base = base_value(item_a) / max(base_value(item_b), 0.01)
    scarcity_a = 1.0 / max(world_stock.get(item_a, 0), 1)
    scarcity_b = 1.0 / max(world_stock.get(item_b, 0), 1)
    return base * (scarcity_b / scarcity_a)


def fair_trade_qty(
    item_a: str,
    qty_a: int,
    item_b: str,
    world_stock: dict[str, int],
) -> int:
    """qty_a 단위 item_a의 공정 교환 item_b 수량."""
    rate = exchange_rate(item_a, item_b, world_stock)
    return max(1, round(qty_a * rate))
