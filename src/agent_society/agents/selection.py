"""Utility AI — full action selection for all roles."""

from __future__ import annotations

import logging
import random as _random_module
from random import Random

from agent_society.agents.actions import (
    FOOD_SATISFY,
    ROLE_TOOL,
    AcquireToolAction,
    AcquireWeaponAction,
    BuyAction,
    CollectFromNodeAction,
    ConsumeFoodAction,
    CraftAction,
    DeliverToNodeAction,
    NodeTransferAction,
    NoAction,
    ProduceAction,
    RaidAction,
    SellAction,
    TradeAction,
    TravelAction,
)
from agent_society.economy.config import CONFIG, MERCHANT_MIN_MARGIN, NORMAL_STOCKPILE, units_per_meal
from agent_society.economy.equilibrium import suggest_stockpile_cap
from agent_society.economy.exchange import node_price
from agent_society.agents.travel_planner import has_goods_to_trade, next_hop, should_use_risky_route
from agent_society.world.hex_map import AMBUSH_PROB, RISKY_ROUTE_IDS, RISKY_TILE_SET, SAFE_ROUTE_IDS
from agent_society.agents.roles import ROLE_CATALOG
from agent_society.schema import Agent, NeedType, RaiderFaction, RegionType, Role
from agent_society.world import world as world_ops
from agent_society.world.snapshot import WorldSnapshot

log = logging.getLogger(__name__)

FOOD_GOODS = ("cooked_meal", "fruit", "meat", "wheat")   # preference order
SURPLUS_THRESHOLD = 1    # inventory qty above which agent will trade away a good
TRADE_SCORE = 0.8        # relative to hunger score (hunger always prioritised)

# Canonical node IDs
CITY_NODE = "city"
FARM_NODE = "farm"
RAIDER_HOME = "raider.hideout"


# ── Public entry point ────────────────────────────────────────────────────────

def select_action(agent: Agent, snapshot: WorldSnapshot, rng: Random | None = None) -> object:
    """Return the highest-scoring action for this agent this tick."""
    if rng is None:
        rng = _random_module  # type: ignore[assignment]
    if isinstance(agent, RaiderFaction):
        return _select_raider(agent, snapshot, rng)
    if agent.role == Role.MERCHANT:
        return _select_merchant(agent, snapshot, rng)
    if agent.role == Role.BLACKSMITH:
        return _select_blacksmith(agent, snapshot)
    if agent.role == Role.COOK:
        return _select_cook(agent, snapshot)
    return _select_producer(agent, snapshot)


# ── Role-specific selectors ───────────────────────────────────────────────────

def _good_cap(good: str) -> int:
    """Dynamic per-good production cap derived from current NORMAL_STOCKPILE."""
    return suggest_stockpile_cap(good, NORMAL_STOCKPILE.get(good, 10))


def _select_producer(agent: Agent, snapshot: WorldSnapshot) -> object:
    """Farmer / Herder / Miner / Orchardist — all live at the single 'farm' node."""
    scores: list[tuple[float, object]] = []

    # 1. Eat if hungry — farm stockpile carries all food
    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    meal = _food_at_node(agent, snapshot)
    if hunger > 0.5 and meal:
        food, food_qty = meal
        scores.append((hunger, ConsumeFoodAction(
            agent=agent, food_good=food, node_id=agent.current_node, qty=food_qty,
        )))

    # 2. Tool acquisition — skip if we can't afford it (else we'd retry every
    #    tick in a gold-starved loop)
    tool_type = ROLE_TOOL.get(agent.role.value, "")
    tool_need = agent.needs.get(NeedType.TOOL_NEED, 0.0)
    if tool_type and (tool_need > 0.2 or agent.get_tool_durability(tool_type) < 2.0):
        from agent_society.economy.config import BASE_VALUE
        cost = max(1, round(BASE_VALUE.get(tool_type, 4.0) * 1.5))
        node = snapshot.get_node(agent.current_node)
        if node.stockpile.get(tool_type, 0) > 0 and agent.gold >= cost:
            scores.append((0.95, AcquireToolAction(
                agent=agent, node_id=agent.current_node, tool_type=tool_type,
            )))

    # 3. Produce primary good if farm stockpile under cap
    role_def = ROLE_CATALOG.get(agent.role)
    if role_def and role_def.primary_good:
        good = role_def.primary_good
        node = snapshot.get_node(agent.current_node)
        qty = node.stockpile.get(good, 0)
        if qty < _good_cap(good):
            scarcity = snapshot.scarcity(good)
            scores.append((0.65 + scarcity * 0.35, ProduceAction(
                agent=agent, node_id=agent.current_node, good=good,
            )))

    return _pick_best(scores, agent)


def _select_blacksmith(agent: Agent, snapshot: WorldSnapshot) -> object:
    scores: list[tuple[float, object]] = []

    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    meal = _food_at_node(agent, snapshot)
    if hunger > 0.5 and meal:
        food, food_qty = meal
        scores.append((hunger, ConsumeFoodAction(
            agent=agent, food_good=food, node_id=agent.current_node, qty=food_qty,
        )))

    node = snapshot.get_node(agent.current_node)  # == "city"
    ore_local = node.stockpile.get("ore", 0)

    # Craft when world-wide stock is below the equilibrium cap.
    # Using NORMAL_STOCKPILE (population-scaled) instead of absolute scarcity
    # keeps craft activity right-sized as agent counts change.
    def _need(good: str, headroom: float = 1.5) -> float:
        total = sum(n.stockpile.get(good, 0) for n in _snapshot_world(snapshot).nodes.values())
        normal = NORMAL_STOCKPILE.get(good, 10)
        target = max(3, normal * headroom)
        if total >= target:
            return 0.0
        # 1.0 when empty, 0.0 when at/above target
        return max(0.0, 1.0 - total / target)

    # Sword/plow (2 ore each) — prefer whichever is more needed
    if ore_local >= 2:
        sword_need = _need("sword")
        plow_need  = _need("plow")
        if sword_need > 0 and sword_need >= plow_need:
            scores.append((0.70 + 0.25 * sword_need, CraftAction(
                agent=agent, node_id=agent.current_node,
                output_good="sword", inputs={"ore": 2}, output_amount=1,
            )))
        elif plow_need > 0:
            scores.append((0.70 + 0.25 * plow_need, CraftAction(
                agent=agent, node_id=agent.current_node,
                output_good="plow", inputs={"ore": 2}, output_amount=1,
            )))

    # Single-ore tools
    if ore_local >= 1:
        for tool in ("sickle", "pickaxe", "cooking_tools", "pruning_shears"):
            need = _need(tool)
            if need > 0:
                scores.append((0.65 + 0.25 * need, CraftAction(
                    agent=agent, node_id=agent.current_node,
                    output_good=tool, inputs={"ore": 1}, output_amount=1,
                )))

    return _pick_best(scores, agent)


def _select_cook(agent: Agent, snapshot: WorldSnapshot) -> object:
    scores: list[tuple[float, object]] = []

    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    meal = _food_at_node(agent, snapshot)
    if hunger > 0.5 and meal:
        food, food_qty = meal
        scores.append((hunger, ConsumeFoodAction(
            agent=agent, food_good=food, node_id=agent.current_node, qty=food_qty,
        )))

    node = snapshot.get_node(agent.current_node)  # == "city"
    wheat_local = node.stockpile.get("wheat", 0)
    meat_local  = node.stockpile.get("meat", 0)
    fruit_local = node.stockpile.get("fruit", 0)

    # Tool acquisition — cook needs cooking_tools (skip if broke)
    cook_tool_need = agent.needs.get(NeedType.TOOL_NEED, 0.0)
    if cook_tool_need > 0.2 or agent.get_tool_durability("cooking_tools") < 2.0:
        from agent_society.economy.config import BASE_VALUE
        ct_cost = max(1, round(BASE_VALUE.get("cooking_tools", 4.0) * 1.5))
        if node.stockpile.get("cooking_tools", 0) > 0 and agent.gold >= ct_cost:
            scores.append((0.95, AcquireToolAction(
                agent=agent, node_id=agent.current_node, tool_type="cooking_tools",
            )))

    scarcity = snapshot.scarcity("cooked_meal")
    # Lighter wheat footprint: prefer wheat+meat combo (1+1) and accept fruit-based fallback.
    if wheat_local >= 1 and meat_local >= 1:
        scores.append((0.85 * max(scarcity, 0.3), CraftAction(
            agent=agent, node_id=agent.current_node,
            output_good="cooked_meal", inputs={"wheat": 1, "meat": 1}, output_amount=1,
        )))
    elif wheat_local >= 1 and fruit_local >= 1:
        scores.append((0.75 * max(scarcity, 0.3), CraftAction(
            agent=agent, node_id=agent.current_node,
            output_good="cooked_meal", inputs={"wheat": 1, "fruit": 1}, output_amount=1,
        )))
    elif wheat_local >= 2:
        scores.append((0.6 * max(scarcity, 0.3), CraftAction(
            agent=agent, node_id=agent.current_node,
            output_good="cooked_meal", inputs={"wheat": 2}, output_amount=1,
        )))

    return _pick_best(scores, agent)


MERCHANT_CARRY_CAP = CONFIG.merchant_carry_cap
_FARM_GOODS = {"wheat", "meat", "ore", "fruit"}
_CITY_GOODS = {"cooked_meal", "plow", "sickle", "pickaxe", "pruning_shears"}


def _merchant_effective_cap(agent: Agent) -> int:
    """Carry cap minus weapons held — each weapon occupies one hand slot."""
    weapons_held = 1 if agent.has_usable_weapon() else 0
    return max(1, MERCHANT_CARRY_CAP - weapons_held)


def _select_merchant(agent: Agent, snapshot: WorldSnapshot, rng: Random) -> object:
    scores: list[tuple[float, object]] = []

    # 1. Eat first if very hungry
    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    meal = _food_at_node(agent, snapshot)
    if hunger > 0.5 and meal:
        food, food_qty = meal
        scores.append((hunger, ConsumeFoodAction(
            agent=agent, food_good=food, node_id=agent.current_node, qty=food_qty,
        )))

    inv_total = sum(v for k, v in agent.inventory.items() if not k.startswith("_"))
    effective_cap = _merchant_effective_cap(agent)
    at_city = agent.current_node == CITY_NODE
    at_farm = agent.current_node == FARM_NODE

    # 2a. At farm: deliver any city goods (cooked_meal, tools) we carried over
    if at_farm:
        for good in _CITY_GOODS:
            carrying = agent.inventory.get(good, 0)
            if carrying > 0:
                scores.append((0.94, DeliverToNodeAction(
                    agent=agent, deposit_node=FARM_NODE, good=good, qty=carrying,
                )))

    # 2b. At farm: collect farm surplus to ship to city
    _CITY_DEMAND_CAP = CONFIG.city_demand_cap
    if at_farm and inv_total < effective_cap:
        farm_node = snapshot.get_node(FARM_NODE)
        city_node = snapshot.get_node(CITY_NODE)
        for good in _FARM_GOODS:
            qty = farm_node.stockpile.get(good, 0)
            city_qty = city_node.stockpile.get(good, 0)
            if qty > 5 and city_qty < _CITY_DEMAND_CAP:
                take = min(4, qty - 5)
                scores.append((0.90 + rng.uniform(0, 0.04), CollectFromNodeAction(
                    agent=agent, node_id=FARM_NODE, good=good, qty=take,
                )))

    # 3. At city: deliver farm goods we carried over
    if at_city:
        for good in _FARM_GOODS:
            qty = agent.inventory.get(good, 0)
            if qty > 0:
                scores.append((0.94, DeliverToNodeAction(
                    agent=agent, deposit_node=CITY_NODE, good=good, qty=qty,
                )))

        # 3b. Collect city surplus for return trip (only when not already loaded with farm goods)
        farm_goods_carried = sum(agent.inventory.get(g, 0) for g in _FARM_GOODS)
        if farm_goods_carried == 0 and inv_total < effective_cap:
            city_node = snapshot.get_node(CITY_NODE)
            farm_node = snapshot.get_node(FARM_NODE)
            # Ship cooked_meal when city has surplus and farm is low
            cooked_city = city_node.stockpile.get("cooked_meal", 0)
            cooked_farm = farm_node.stockpile.get("cooked_meal", 0)
            if cooked_city > 15 and cooked_farm < 10:
                take = min(4, cooked_city - 15)
                scores.append((0.91, CollectFromNodeAction(
                    agent=agent, node_id=CITY_NODE, good="cooked_meal", qty=take,
                )))
            # Ship tools when farm is low on any of them
            _FARM_TOOLS = ("plow", "sickle", "pickaxe", "pruning_shears")
            for farm_tool in _FARM_TOOLS:
                if farm_node.stockpile.get(farm_tool, 0) < 3 and city_node.stockpile.get(farm_tool, 0) > 0:
                    take = min(2, city_node.stockpile.get(farm_tool, 0))
                    scores.append((0.89, CollectFromNodeAction(
                        agent=agent, node_id=CITY_NODE, good=farm_tool, qty=take,
                    )))
                    break  # one tool type per trip

        # 3c. Buy weapon when feeling unsafe and inside the city
        safety = agent.needs.get(NeedType.SAFETY, 0.0)
        if safety > 0.25 and not agent.has_usable_weapon():
            city_node = snapshot.get_node(CITY_NODE)
            if city_node.stockpile.get("sword", 0) > 0:
                scores.append((0.92, AcquireWeaponAction(
                    agent=agent, source_node=CITY_NODE,
                )))

    # 4. Travel (slight rng jitter to desynchronise merchants)
    world = _snapshot_world(snapshot)
    if world:
        hop = next_hop(agent, world)
        if hop:
            cargo_ratio = inv_total / max(1, effective_cap)
            if should_use_risky_route(agent) and cargo_ratio > 0.5:
                # Armed + heading risky + reasonably loaded: go fast
                travel_score = 0.91 + rng.uniform(0, 0.02)
            else:
                travel_score = 0.86 + rng.uniform(0, 0.04)
            scores.append((travel_score, TravelAction(agent=agent, target_node=hop)))

    # 5. Gold-based market trade (arbitrage)
    arb = _merchant_market_action(agent, snapshot)
    if arb is not None:
        scores.append(arb)

    # 6. Barter with non-merchant in same region (fallback)
    trade = _best_trade_non_merchant_region(agent, snapshot)
    if trade:
        scores.append((TRADE_SCORE, trade))

    return _pick_best(scores, agent)


def _select_raider(agent: RaiderFaction, snapshot: WorldSnapshot, rng: Random) -> object:
    """Raider always ambushes — eats only when starving, raids regardless of hunger.

    Ambush probability scales with tile proximity to hideout (see hex_map.AMBUSH_PROB).
    Risky route tiles are checked each tick; safe route tiles only when very hungry.
    """
    hunger = agent.needs.get(NeedType.HUNGER, 0.0)

    # 1. Check all risky route tiles — probability decreases with distance from hideout
    for tile_id in RISKY_ROUTE_IDS:
        prob = AMBUSH_PROB.get(tile_id, 0.0)
        merchants = [a for a in snapshot.agents_at(tile_id) if a.role == Role.MERCHANT]
        if merchants and rng.random() < prob:
            return RaidAction(raider=agent, target_node=tile_id)

    # 1b. Desperate hunger — extend raids to safe route tiles nearest the hideout
    if hunger >= 0.8:
        for tile_id in SAFE_ROUTE_IDS:
            prob = AMBUSH_PROB.get(tile_id, 0.0)
            if prob <= 0.0:
                continue
            merchants = [a for a in snapshot.agents_at(tile_id) if a.role == Role.MERCHANT]
            if merchants and rng.random() < prob:
                return RaidAction(raider=agent, target_node=tile_id)

    # 2. Eat only when very hungry (after raid opportunity checked)
    if hunger > 0.6:
        if agent.current_node == RAIDER_HOME:
            node = snapshot.get_node(RAIDER_HOME)
            for good in FOOD_GOODS:
                if node.stockpile.get(good, 0) > 0:
                    return ConsumeFoodAction(agent=agent, food_good=good, node_id=RAIDER_HOME)
        for good in FOOD_GOODS:
            if agent.inventory.get(good, 0) > 0:
                return ConsumeFoodAction(agent=agent, food_good=good, node_id=agent.current_node)

    # 3. Return home if strayed outside territory
    if agent.current_node not in ({RAIDER_HOME} | RISKY_TILE_SET):
        return TravelAction(agent=agent, target_node=RAIDER_HOME)

    return NoAction(agent=agent)


# ── Helpers ───────────────────────────────────────────────────────────────────

# Goods eligible for gold-based arbitrage (tools handled by dedicated deliver/collect logic)
_TRADEABLE_GOODS = ("wheat", "meat", "fruit", "ore", "cooked_meal")
_TRADE_NODES = {CITY_NODE, FARM_NODE}


def _merchant_market_action(
    agent: Agent,
    snapshot: WorldSnapshot,
) -> tuple[float, object] | None:
    """Gold 기반 차익거래 — city/farm hub에서만 발동."""
    if agent.current_node not in _TRADE_NODES:
        return None

    world = _snapshot_world(snapshot)
    if world is None:
        return None

    cur_node = world.nodes.get(agent.current_node)
    if cur_node is None:
        return None

    total_gold = sum(getattr(a, "gold", 0) for a in world.agents.values())

    # --- SELL: 인벤토리에 있는 재화를 현재 노드에서 팔기 ---
    # Only proposes a SellAction if the local market actually has gold to pay
    # — otherwise the action would fail and the merchant would loop forever
    # on the same item with revenue=0.
    co_located_gold = sum(
        world.agents[aid].gold
        for aid in world.agents_by_node.get(agent.current_node, [])
        if aid != agent.id and aid in world.agents
    )
    buying_capacity = cur_node.gold + co_located_gold

    best_sell: tuple[float, object] | None = None
    for good in _TRADEABLE_GOODS:
        qty = agent.inventory.get(good, 0)
        if qty <= 0:
            continue
        sell_price = node_price(cur_node.stockpile, good, total_gold)
        if buying_capacity < sell_price:
            continue   # no one here can pay; come back later
        buy_prices = [
            node_price(n.stockpile, good, total_gold)
            for nid, n in world.nodes.items()
            if nid != agent.current_node
        ]
        min_buy = min(buy_prices) if buy_prices else sell_price
        margin = sell_price - min_buy
        if margin >= MERCHANT_MIN_MARGIN:
            # Sell only as much as the market can absorb this tick.
            sellable_qty = min(qty, max(1, int(buying_capacity // sell_price)))
            score = 0.95 + min(0.03, margin / 20.0)
            action = SellAction(
                agent=agent, node_id=agent.current_node,
                good=good, qty=sellable_qty, unit_price=sell_price,
            )
            if best_sell is None or score > best_sell[0]:
                best_sell = (score, action)

    if best_sell:
        return best_sell

    # --- BUY: 현재 노드에서 싼 재화를 사기 ---
    _MERCHANT_GOLD_RESERVE = CONFIG.merchant_gold_reserve
    effective_cap = _merchant_effective_cap(agent)
    inv_total = sum(v for k, v in agent.inventory.items() if not k.startswith("_"))
    space = effective_cap - inv_total
    spendable = agent.gold - _MERCHANT_GOLD_RESERVE
    if spendable <= 0 or space <= 0:
        return None

    best_buy: tuple[float, object] | None = None
    for good in _TRADEABLE_GOODS:
        buy_price = node_price(cur_node.stockpile, good, total_gold)
        if cur_node.stockpile.get(good, 0) <= 2:
            continue
        sell_prices = [
            node_price(n.stockpile, good, total_gold)
            for nid, n in world.nodes.items()
            if nid != agent.current_node
        ]
        max_sell = max(sell_prices) if sell_prices else buy_price
        margin = max_sell - buy_price
        if margin >= MERCHANT_MIN_MARGIN:
            affordable = min(space, int(spendable // buy_price) if buy_price > 0 else 0)
            qty = min(affordable, cur_node.stockpile.get(good, 0) - 2)
            if qty <= 0:
                continue
            score = 0.95 + min(0.03, margin / 20.0)
            action = BuyAction(
                agent=agent, node_id=agent.current_node,
                good=good, qty=qty, unit_price=buy_price,
            )
            if best_buy is None or score > best_buy[0]:
                best_buy = (score, action)

    return best_buy


def _food_at_node(agent: Agent, snapshot: WorldSnapshot) -> tuple[str, int] | None:
    """Pick a food to eat here and how many units to consume for one meal.

    Priority:
      1. Food in the agent's own inventory (free — wage-kept produce)
      2. Stockpile food the agent produces themselves (free — self-sufficiency)
      3. Stockpile food the agent can afford to buy
    """
    from agent_society.economy.routing import PRODUCER_OF
    node = snapshot.get_node(agent.current_node)

    # 1. Inventory food — free, no gold check
    for good in FOOD_GOODS:
        have = agent.inventory.get(good, 0)
        if have <= 0:
            continue
        need = units_per_meal(good)
        return good, min(need, have)

    # 2. Self-produced food at node stockpile — free (farmer at farm eating wheat)
    for good in FOOD_GOODS:
        if PRODUCER_OF.get(good) != agent.role:
            continue
        avail = node.stockpile.get(good, 0)
        if avail <= 0:
            continue
        need = units_per_meal(good)
        return good, min(need, avail)

    # 3. Stockpile food we have to buy — pick one we can afford a full meal of
    world = _snapshot_world(snapshot)
    total_gold = sum(getattr(a, "gold", 0) for a in world.agents.values()) if world else 0
    for good in FOOD_GOODS:
        need = units_per_meal(good)
        avail = node.stockpile.get(good, 0)
        if avail < need:
            continue
        price_per = max(1, round(node_price(node.stockpile, good, total_gold)))
        if agent.gold >= price_per * need:
            return good, need

    # 4. Partial meal of whatever we can afford at least 1 unit of
    for good in FOOD_GOODS:
        avail = node.stockpile.get(good, 0)
        if avail <= 0:
            continue
        price_per = max(1, round(node_price(node.stockpile, good, total_gold))) if world else 1
        affordable = agent.gold // price_per
        if affordable > 0:
            return good, min(avail, affordable)
    return None


def _best_trade_1hop(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    others = [a for a in snapshot.agents_within_1_hop(agent.current_node)
              if a.id != agent.id]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade_non_merchant(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    others = [a for a in snapshot.agents_at(agent.current_node)
              if a.id != agent.id and a.role != Role.MERCHANT]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade_non_merchant_region(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    others = [a for a in snapshot.agents_within_1_hop(agent.current_node)
              if a.id != agent.id and a.role != Role.MERCHANT]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    others = [a for a in snapshot.agents_at(agent.current_node) if a.id != agent.id]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade_region(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    cur_region = snapshot.get_node(agent.current_node).region
    others = [a for a in snapshot.agents_in_region(cur_region) if a.id != agent.id]
    return _find_best_trade_with(agent, others, snapshot)


def _find_best_trade_with(agent: Agent, others: list, snapshot: WorldSnapshot) -> TradeAction | None:
    if not others:
        return None

    best_score = 0.0
    best_action: TradeAction | None = None

    for buyer in others:
        for item_out, qty_out in agent.inventory.items():
            if item_out.startswith("_") or qty_out <= SURPLUS_THRESHOLD:
                continue
            for item_in, qty_in_buyer in buyer.inventory.items():
                if item_in.startswith("_") or qty_in_buyer <= SURPLUS_THRESHOLD:
                    continue
                if item_in == item_out:
                    continue
                score = (snapshot.scarcity(item_out) + snapshot.scarcity(item_in)) * TRADE_SCORE
                if score > best_score:
                    best_score = score
                    qty_in = max(1, qty_in_buyer // 2)
                    best_action = TradeAction(
                        agent=agent, buyer=buyer,
                        item_out=item_out, item_in=item_in,
                        qty_out=min(qty_out, 2), qty_in=qty_in,
                    )

    return best_action


def _pick_best(scores: list[tuple[float, object]], agent: Agent) -> object:
    if not scores:
        return NoAction(agent=agent)
    scores.sort(key=lambda x: x[0], reverse=True)
    return scores[0][1]


def _snapshot_world(snapshot: WorldSnapshot):
    """Access the underlying World from snapshot (private attr)."""
    return getattr(snapshot, "_world", None)
