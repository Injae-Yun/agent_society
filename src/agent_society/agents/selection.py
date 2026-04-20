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
from agent_society.config.balance import MERCHANT_MIN_MARGIN
from agent_society.economy.exchange import node_price
from agent_society.agents.travel_planner import has_goods_to_trade, next_hop, should_use_risky_route
from agent_society.agents.roles import ROLE_CATALOG
from agent_society.schema import Agent, NeedType, RaiderFaction, RegionType, Role
from agent_society.world import world as world_ops
from agent_society.world.snapshot import WorldSnapshot

log = logging.getLogger(__name__)

FOOD_GOODS = ("cooked_meal", "fruit", "meat", "wheat")   # preference order
SURPLUS_THRESHOLD = 1    # inventory qty above which agent will trade away a good
TRADE_SCORE = 0.8        # relative to hunger score (hunger always prioritised)

# Raider geography
RAIDER_HOME = "raider.hideout"
RISKY_MID = "route.risky_mid"
SAFE_MID = "route.safe_mid"

# Raider ambush probability per tick when a merchant is at RISKY_MID.
# 2-tick transit: escape probability = (1 - p)^2.
# At p=0.65: ~12% full escape — risky but survivable.
# At p=0.35 (old): ~42% escape — too lenient; merchants under-priced the route.
AMBUSH_PROB_RISKY = 0.65


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

_FARM_HUB = "farm.hub"
_LOCAL_STOCKPILE_CAP = 15   # produce until node hits this
_HUB_STOCKPILE_CAP   = 25   # stop depositing if hub already full
_DEPOSIT_QTY         = 5    # units pushed per deposit action


def _select_producer(agent: Agent, snapshot: WorldSnapshot) -> object:
    """Farmer / Herder / Miner / Orchardist.

    Hub model: produce into local node stockpile, then deposit surplus to
    farm.hub. No direct peer-to-peer trading — the market hub handles exchange.
    """
    scores: list[tuple[float, object]] = []

    # 1. Eat if hungry — prefer local food; fall back to collecting from farm.hub
    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    food = _food_at_node(agent, snapshot)
    if hunger > 0.5 and food:
        scores.append((hunger, ConsumeFoodAction(agent=agent, food_good=food, node_id=agent.current_node)))
    elif hunger > 0.6:
        # No local food — try to collect cooked_meal from farm.hub (1-hop away)
        hub_cooked = snapshot.get_node(_FARM_HUB).stockpile.get("cooked_meal", 0)
        if hub_cooked > 5:
            scores.append((hunger * 0.85, CollectFromNodeAction(
                agent=agent, node_id=_FARM_HUB, good="cooked_meal", qty=1,
            )))

    # Tool acquisition — when tool is worn/broken, try to replace from local node or farm.hub
    tool_type = ROLE_TOOL.get(agent.role.value, "")
    tool_need = agent.needs.get(NeedType.TOOL_NEED, 0.0)
    if tool_type and (tool_need > 0.2 or agent.get_tool_durability(tool_type) < 2.0):
        local_node = snapshot.get_node(agent.current_node)
        if local_node.stockpile.get(tool_type, 0) > 0:
            scores.append((0.95, AcquireToolAction(agent=agent, node_id=agent.current_node, tool_type=tool_type)))
        elif agent.current_node != _FARM_HUB:
            hub = snapshot.get_node(_FARM_HUB)
            if hub.stockpile.get(tool_type, 0) > 0:
                scores.append((0.90, AcquireToolAction(agent=agent, node_id=_FARM_HUB, tool_type=tool_type)))

    role_def = ROLE_CATALOG.get(agent.role)
    if role_def and role_def.primary_good:
        good = role_def.primary_good
        node = snapshot.get_node(agent.current_node)
        local_qty = node.stockpile.get(good, 0)

        if local_qty < _LOCAL_STOCKPILE_CAP:
            # 2. Produce — base score 0.65 always beats any secondary action
            scarcity = snapshot.scarcity(good)
            scores.append((0.65 + scarcity * 0.35, ProduceAction(
                agent=agent, node_id=agent.current_node, good=good,
            )))
        else:
            # 3. Local cap reached → deposit surplus to farm.hub (hub model)
            hub_qty = snapshot.get_node(_FARM_HUB).stockpile.get(good, 0)
            if hub_qty < _HUB_STOCKPILE_CAP:
                scores.append((0.60, NodeTransferAction(
                    agent=agent,
                    source_node=agent.current_node,
                    dest_node=_FARM_HUB,
                    good=good,
                    qty=_DEPOSIT_QTY,
                )))

    return _pick_best(scores, agent)


_CITY_MARKET = "city.market"
_FOOD_GOODS_ORDER = ("cooked_meal", "fruit", "meat", "wheat")


def _select_blacksmith(agent: Agent, snapshot: WorldSnapshot) -> object:
    scores: list[tuple[float, object]] = []

    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    food = _food_at_node(agent, snapshot)
    if hunger > 0.5 and food:
        scores.append((hunger, ConsumeFoodAction(agent=agent, food_good=food, node_id=agent.current_node)))
    elif hunger > 0.5:
        # No food at node/inventory — collect from city.market (1-hop away)
        market = snapshot.get_node(_CITY_MARKET)
        for good in _FOOD_GOODS_ORDER:
            if market.stockpile.get(good, 0) > 0:
                scores.append((hunger * 0.85, CollectFromNodeAction(
                    agent=agent, node_id=_CITY_MARKET, good=good, qty=1,
                )))
                break

    node = snapshot.get_node(agent.current_node)
    ore_local = node.stockpile.get("ore", 0)

    # Restock ore from adjacent nodes (city.market is 1 hop) if running low
    if ore_local < 8:
        world = _snapshot_world(snapshot)
        if world:
            for edge in world_ops.edges_from(world, agent.current_node):
                neighbor = edge.v if edge.u == agent.current_node else edge.u
                n_node = snapshot.get_node(neighbor)
                ore_there = n_node.stockpile.get("ore", 0)
                if ore_there >= 2:
                    scores.append((0.95, NodeTransferAction(
                        agent=agent, source_node=neighbor, dest_node=agent.current_node,
                        good="ore", qty=min(8, ore_there),
                    )))

    # Craft thresholds — stop producing when world stock is already sufficient.
    # scarcity = 1/total: 0.05 → 20 units, 0.10 → 10 units in world.
    _WEAPON_SCARCITY_MIN = 0.04   # craft sword/plow only if fewer than ~25 in world
    _TOOL_SCARCITY_MIN   = 0.07   # craft sickle/pickaxe/cooking_tools if fewer than ~14

    # Craft sword if ore available (swords enable merchant self-defense)
    if ore_local >= 2:
        sword_scarcity = snapshot.scarcity("sword")
        plow_scarcity = snapshot.scarcity("plow")
        if sword_scarcity >= plow_scarcity and sword_scarcity >= _WEAPON_SCARCITY_MIN:
            scores.append((0.9 * sword_scarcity, CraftAction(
                agent=agent, node_id=agent.current_node,
                output_good="sword", inputs={"ore": 2}, output_amount=1,
            )))
        elif plow_scarcity >= _WEAPON_SCARCITY_MIN:
            scores.append((0.9 * plow_scarcity, CraftAction(
                agent=agent, node_id=agent.current_node,
                output_good="plow", inputs={"ore": 2}, output_amount=1,
            )))

    # Craft sickle / pickaxe / cooking_tools
    if ore_local >= 1:
        for tool, sc in [("sickle", snapshot.scarcity("sickle")),
                         ("pickaxe", snapshot.scarcity("pickaxe")),
                         ("cooking_tools", snapshot.scarcity("cooking_tools"))]:
            if sc >= _TOOL_SCARCITY_MIN:
                scores.append((0.85 * sc, CraftAction(
                    agent=agent, node_id=agent.current_node,
                    output_good=tool, inputs={"ore": 1}, output_amount=1,
                )))

    return _pick_best(scores, agent)


def _select_cook(agent: Agent, snapshot: WorldSnapshot) -> object:
    scores: list[tuple[float, object]] = []

    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    food = _food_at_node(agent, snapshot)
    if hunger > 0.5 and food:
        scores.append((hunger, ConsumeFoodAction(agent=agent, food_good=food, node_id=agent.current_node)))
    elif hunger > 0.5:
        # No food at kitchen — collect from city.market (1-hop)
        market = snapshot.get_node(_CITY_MARKET)
        for good in _FOOD_GOODS_ORDER:
            if market.stockpile.get(good, 0) > 0:
                scores.append((hunger * 0.85, CollectFromNodeAction(
                    agent=agent, node_id=_CITY_MARKET, good=good, qty=1,
                )))
                break

    node = snapshot.get_node(agent.current_node)
    wheat_local = node.stockpile.get("wheat", 0)
    meat_local  = node.stockpile.get("meat", 0)
    fruit_local_cook = node.stockpile.get("fruit", 0)

    # Restock ingredients from adjacent nodes (city.market is 1 hop)
    world = _snapshot_world(snapshot)
    if world:
        for edge in world_ops.edges_from(world, agent.current_node):
            neighbor = edge.v if edge.u == agent.current_node else edge.u
            n_node = snapshot.get_node(neighbor)
            for good, local_qty in (("wheat", wheat_local), ("meat", meat_local), ("fruit", fruit_local_cook)):
                if local_qty < 3:
                    there = n_node.stockpile.get(good, 0)
                    if there >= 2:
                        scores.append((0.95, NodeTransferAction(
                            agent=agent, source_node=neighbor, dest_node=agent.current_node,
                            good=good, qty=min(5, there),
                        )))

    # Tool acquisition — cook needs cooking_tools; check kitchen then smithy
    cook_tool_need = agent.needs.get(NeedType.TOOL_NEED, 0.0)
    if cook_tool_need > 0.2 or agent.get_tool_durability("cooking_tools") < 2.0:
        if node.stockpile.get("cooking_tools", 0) > 0:
            scores.append((0.95, AcquireToolAction(agent=agent, node_id=agent.current_node, tool_type="cooking_tools")))
        else:
            smithy = snapshot.get_node(_CITY_MARKET.replace("market", "smithy"))
            if smithy.stockpile.get("cooking_tools", 0) > 0:
                scores.append((0.90, AcquireToolAction(agent=agent, node_id="city.smithy", tool_type="cooking_tools")))

    fruit_local = node.stockpile.get("fruit", 0)
    scarcity = snapshot.scarcity("cooked_meal")
    if wheat_local >= 2 and meat_local >= 1:
        scores.append((0.85 * max(scarcity, 0.3), CraftAction(
            agent=agent, node_id=agent.current_node,
            output_good="cooked_meal", inputs={"wheat": 2, "meat": 1}, output_amount=1,
        )))
    elif wheat_local >= 2 and fruit_local >= 1:
        scores.append((0.75 * max(scarcity, 0.3), CraftAction(
            agent=agent, node_id=agent.current_node,
            output_good="cooked_meal", inputs={"wheat": 2, "fruit": 1}, output_amount=1,
        )))
    elif wheat_local >= 3:
        scores.append((0.6 * max(scarcity, 0.3), CraftAction(
            agent=agent, node_id=agent.current_node,
            output_good="cooked_meal", inputs={"wheat": 3}, output_amount=1,
        )))

    return _pick_best(scores, agent)


MERCHANT_CARRY_CAP = 10   # max inventory units before merchant heads to city
# All farm goods delivered to city.market (single hub — crafters fetch from there)
_FARM_COLLECT_GOODS = {"wheat", "meat", "ore", "fruit"}


def _merchant_effective_cap(agent: Agent) -> int:
    """Carry cap minus weapons held — each weapon occupies one hand slot.

    An armed merchant has less room for trade goods.  This is the primary
    disincentive for arming: opportunity cost of cargo space.
    """
    weapons_held = 1 if agent.has_usable_weapon() else 0
    return max(1, MERCHANT_CARRY_CAP - weapons_held)


def _select_merchant(agent: Agent, snapshot: WorldSnapshot, rng: Random) -> object:
    scores: list[tuple[float, object]] = []

    # 1. Eat first if very hungry
    hunger = agent.needs.get(NeedType.HUNGER, 0.0)
    food = _food_at_node(agent, snapshot)
    if hunger > 0.5 and food:
        scores.append((hunger, ConsumeFoodAction(agent=agent, food_good=food, node_id=agent.current_node)))

    cur_region = snapshot.get_node(agent.current_node).region
    inv_total = sum(v for k, v in agent.inventory.items() if not k.startswith("_"))
    effective_cap = _merchant_effective_cap(agent)

    # 2a. At farm.hub: deposit cooked_meal and any tools carried from city
    _FARM_TOOLS = ("plow", "sickle", "pickaxe", "pruning_shears")
    if agent.current_node == "farm.hub":
        cooked_carrying = agent.inventory.get("cooked_meal", 0)
        if cooked_carrying > 0:
            scores.append((0.94, DeliverToNodeAction(
                agent=agent, deposit_node="farm.hub", good="cooked_meal", qty=cooked_carrying,
            )))
        for farm_tool in _FARM_TOOLS:
            tool_carrying = agent.inventory.get(farm_tool, 0)
            if tool_carrying > 0:
                scores.append((0.94, DeliverToNodeAction(
                    agent=agent, deposit_node="farm.hub", good=farm_tool, qty=tool_carrying,
                )))

    # 2b. At farm.hub: collect goods for city, but only when city.market actually needs them.
    _CITY_DEMAND_CAP = 30   # don't transport if city.market already has this much
    if agent.current_node == "farm.hub" and inv_total < effective_cap:
        hub_node = snapshot.get_node("farm.hub")
        city_market = snapshot.get_node("city.market")
        for good in _FARM_COLLECT_GOODS:
            qty = hub_node.stockpile.get(good, 0)
            city_qty = city_market.stockpile.get(good, 0)
            if qty > 5 and city_qty < _CITY_DEMAND_CAP:
                take = min(4, qty - 5)
                scores.append((0.90 + rng.uniform(0, 0.04), CollectFromNodeAction(
                    agent=agent, node_id="farm.hub", good=good, qty=take,
                )))

    # 3. At city: deliver all farm goods to city.market (central hub)
    if cur_region == RegionType.CITY:
        for good in _FARM_COLLECT_GOODS:
            qty = agent.inventory.get(good, 0)
            if qty > 0:
                scores.append((0.94, DeliverToNodeAction(
                    agent=agent, deposit_node="city.market", good=good, qty=qty,
                )))
        # 3b. Collect city goods for return trip to farm (only when not carrying farm goods)
        farm_goods_carried = sum(agent.inventory.get(g, 0) for g in _FARM_COLLECT_GOODS)
        if farm_goods_carried == 0 and inv_total < effective_cap:
            # Collect cooked_meal from city.kitchen → deliver to farm.hub
            # Only transport when kitchen has surplus AND farm.hub is running low
            kitchen = snapshot.get_node("city.kitchen")
            cooked_at_kitchen = kitchen.stockpile.get("cooked_meal", 0)
            farm_hub_cooked = snapshot.get_node("farm.hub").stockpile.get("cooked_meal", 0)
            if cooked_at_kitchen > 15 and farm_hub_cooked < 10:
                take = min(4, cooked_at_kitchen - 15)
                scores.append((0.91, CollectFromNodeAction(
                    agent=agent, node_id="city.kitchen", good="cooked_meal", qty=take,
                )))
            # Collect tools from city.smithy when farm.hub is running low
            hub = snapshot.get_node("farm.hub")
            smithy = snapshot.get_node("city.smithy")
            for farm_tool in _FARM_TOOLS:
                if hub.stockpile.get(farm_tool, 0) < 3 and smithy.stockpile.get(farm_tool, 0) > 0:
                    take = min(2, smithy.stockpile.get(farm_tool, 0))
                    scores.append((0.89, CollectFromNodeAction(
                        agent=agent, node_id="city.smithy", good=farm_tool, qty=take,
                    )))
                    break  # one tool type per trip
        # 3d. Buy weapon when feeling unsafe and physically inside the city.
        #     route.safe_mid is technically city-region but we want weapon
        #     purchase to happen at an actual smithy, not on the road.
        _CITY_DISTRICTS = {"city.market", "city.smithy", "city.kitchen", "city.residential"}
        safety = agent.needs.get(NeedType.SAFETY, 0.0)
        if (safety > 0.25 and not agent.has_usable_weapon()
                and agent.current_node in _CITY_DISTRICTS):
            smithy = snapshot.get_node("city.smithy")
            if smithy.stockpile.get("sword", 0) > 0:
                scores.append((0.92, AcquireWeaponAction(
                    agent=agent, source_node="city.smithy",
                )))

    # 4. Travel (slight rng jitter to desynchronise merchants)
    #    Armed merchants heading for the risky route get a speed bonus: faster
    #    delivery means more round trips, so they prioritise moving over collecting
    #    one more unit.
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

    Armory size scales aggression: more swords → higher base hit probability
    and willingness to strike the safer route.
    """
    hunger = agent.needs.get(NeedType.HUNGER, 0.0)

    # 1. Ambush merchants on the risky route — raider territory only.
    #    Probability < 1.0 so merchants have a chance to pass unnoticed.
    risky_merchants = [a for a in snapshot.agents_at(RISKY_MID)
                       if a.role == Role.MERCHANT]
    if risky_merchants and rng.random() < AMBUSH_PROB_RISKY:
        return RaidAction(raider=agent, target_node=RISKY_MID)

    # 1b. Desperate hunger — extend raids to the safe route (10% per tick).
    #     Only triggers when very hungry (>= 0.8) and merchants are present.
    if hunger >= 0.8:
        safe_merchants = [a for a in snapshot.agents_at(SAFE_MID)
                          if a.role == Role.MERCHANT]
        if safe_merchants and rng.random() < 0.10:
            return RaidAction(raider=agent, target_node=SAFE_MID)

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
    if agent.current_node not in (RAIDER_HOME, RISKY_MID):
        return TravelAction(agent=agent, target_node=RAIDER_HOME)

    return NoAction(agent=agent)


# ── Helpers ───────────────────────────────────────────────────────────────────

_TRADEABLE_GOODS = ("wheat", "meat", "fruit", "ore", "cooked_meal", "sword", "plow", "sickle")


def _merchant_market_action(
    agent: Agent,
    snapshot: WorldSnapshot,
) -> tuple[float, object] | None:
    """Gold 기반 차익거래 행동 선택.

    현재 노드에서:
    - 팔 수 있는 재화가 있고 현재 노드 가격이 구매가보다 높으면 → SellAction
    - gold가 있고 현재 노드 재화가 싸고 다른 노드에서 비싸게 팔 수 있으면 → BuyAction
    """
    world = _snapshot_world(snapshot)
    if world is None:
        return None

    cur_node = world.nodes.get(agent.current_node)
    if cur_node is None:
        return None

    # --- SELL: 인벤토리에 있는 재화를 현재 노드에서 팔기 ---
    best_sell: tuple[float, object] | None = None
    for good in _TRADEABLE_GOODS:
        qty = agent.inventory.get(good, 0)
        if qty <= 0:
            continue
        sell_price = node_price(cur_node.stockpile, good)
        # 다른 노드의 구매가와 비교해 실제 차익이 있는 경우만
        buy_prices = [
            node_price(n.stockpile, good)
            for nid, n in world.nodes.items()
            if nid != agent.current_node
        ]
        min_buy = min(buy_prices) if buy_prices else sell_price
        margin = sell_price - min_buy
        if margin >= MERCHANT_MIN_MARGIN:
            score = 0.88 + min(0.08, margin / 20.0)
            action = SellAction(
                agent=agent, node_id=agent.current_node,
                good=good, qty=qty, unit_price=sell_price,
            )
            if best_sell is None or score > best_sell[0]:
                best_sell = (score, action)

    if best_sell:
        return best_sell

    # --- BUY: 현재 노드에서 싼 재화를 사기 (다른 노드에서 비싸게 팔 수 있으면) ---
    effective_cap = _merchant_effective_cap(agent)
    inv_total = sum(v for k, v in agent.inventory.items() if not k.startswith("_"))
    space = effective_cap - inv_total
    if agent.gold <= 0 or space <= 0:
        return None

    best_buy: tuple[float, object] | None = None
    for good in _TRADEABLE_GOODS:
        buy_price = node_price(cur_node.stockpile, good)
        if cur_node.stockpile.get(good, 0) <= 2:
            continue
        sell_prices = [
            node_price(n.stockpile, good)
            for nid, n in world.nodes.items()
            if nid != agent.current_node
        ]
        max_sell = max(sell_prices) if sell_prices else buy_price
        margin = max_sell - buy_price
        if margin >= MERCHANT_MIN_MARGIN:
            affordable = min(space, int(agent.gold // buy_price) if buy_price > 0 else 0)
            qty = min(affordable, cur_node.stockpile.get(good, 0) - 2)
            if qty <= 0:
                continue
            score = 0.85 + min(0.08, margin / 20.0)
            action = BuyAction(
                agent=agent, node_id=agent.current_node,
                good=good, qty=qty, unit_price=buy_price,
            )
            if best_buy is None or score > best_buy[0]:
                best_buy = (score, action)

    return best_buy


def _food_at_node(agent: Agent, snapshot: WorldSnapshot) -> str | None:
    node = snapshot.get_node(agent.current_node)
    for good in FOOD_GOODS:
        if node.stockpile.get(good, 0) > 0:
            return good
        if agent.inventory.get(good, 0) > 0:
            return good
    return None


def _best_trade_1hop(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    """Find the best TradeAction with any agent within 1-hop range."""
    others = [a for a in snapshot.agents_within_1_hop(agent.current_node)
              if a.id != agent.id]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade_non_merchant(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    """Like _best_trade but only trades with non-merchant partners (same node)."""
    others = [a for a in snapshot.agents_at(agent.current_node)
              if a.id != agent.id and a.role != Role.MERCHANT]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade_non_merchant_region(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    """Trade with non-merchant agents within 1-hop range."""
    others = [a for a in snapshot.agents_within_1_hop(agent.current_node)
              if a.id != agent.id and a.role != Role.MERCHANT]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    """Find the best TradeAction with a co-located agent."""
    others = [a for a in snapshot.agents_at(agent.current_node) if a.id != agent.id]
    return _find_best_trade_with(agent, others, snapshot)


def _best_trade_region(agent: Agent, snapshot: WorldSnapshot) -> TradeAction | None:
    """Find the best TradeAction with any co-region agent (not just same node)."""
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
