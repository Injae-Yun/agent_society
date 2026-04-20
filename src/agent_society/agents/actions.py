"""Action dataclasses — each has execute(world, bus) -> dict (resource_delta)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agent_society.agents.needs import satisfy_need
from agent_society.agents.raider import raid_resolution
from agent_society.config.balance import BASE_VALUE, PRODUCE_WAGE
from agent_society.events.bus import WorldEventBus
from agent_society.events.types import EventSeverity, RaidAttempt
from agent_society.schema import Agent, Item, NeedType, RaiderFaction, Tier, World
from agent_society.world import world as world_ops

log = logging.getLogger(__name__)

PRODUCE_AMOUNT = 1       # units produced per tick (base)
INV_WAGE_CAP = 3        # max personal inventory from wage (prevent hoarding)
FOOD_SATISFY = 0.5       # hunger reduction from eating one food item (~8 hour satisfaction)
TOOL_DECAY = 0.1         # durability lost per production action (~100 actions per tool)
TOOL_NEED_SPIKE = 0.3    # need spike when tool is broken

# Role → primary tool type
ROLE_TOOL: dict[str, str] = {
    "farmer": "plow",
    "herder": "sickle",
    "miner": "pickaxe",
    "orchardist": "pruning_shears",
    "cook": "cooking_tools",
}


@dataclass
class NoAction:
    agent: Agent
    action_type: str = field(default="idle", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        return {}


@dataclass
class ProduceAction:
    agent: Agent
    node_id: str
    good: str
    amount: int = PRODUCE_AMOUNT
    action_type: str = field(default="produce", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.node_id)
        if node is None:
            return {}

        # Tool durability check & consume
        tool_type = ROLE_TOOL.get(self.agent.role.value, "")
        if tool_type:
            remaining = self.agent.consume_tool(tool_type, TOOL_DECAY)
            if remaining <= 0.0:
                # Broken tool — spike tool_need, no production
                self.agent.needs[NeedType.TOOL_NEED] = min(
                    1.0, self.agent.needs.get(NeedType.TOOL_NEED, 0.0) + TOOL_NEED_SPIKE
                )
                log.debug("Agent %s tool '%s' broken — no production", self.agent.id, tool_type)
                return {"_tool_broken": tool_type}

        mul = self.agent.inventory.pop("_productivity_mul", 100) / 100.0
        actual = max(1, int(self.amount * mul))
        # Main output goes to node stockpile
        before = node.stockpile.get(self.good, 0)
        node.stockpile[self.good] = before + actual
        # "Wage": keep 1 unit in personal inventory (capped to prevent hoarding)
        cur_inv = self.agent.inventory.get(self.good, 0)
        if cur_inv < INV_WAGE_CAP:
            self.agent.inventory[self.good] = cur_inv + 1
        # Gold 임금: 생산이 gold를 세계에 주입하는 원점
        wage = max(1, int(actual * BASE_VALUE.get(self.good, 1.0) * PRODUCE_WAGE))
        self.agent.gold += wage

        log.debug("Agent %s produced %d %s at %s wage=%dg (tool=%s %.2f)",
                  self.agent.id, actual, self.good, self.node_id, wage, tool_type,
                  self.agent.get_tool_durability(tool_type))
        return {self.node_id: {self.good: actual}}


@dataclass
class CraftAction:
    agent: Agent
    node_id: str
    output_good: str
    inputs: dict[str, int]   # {good: qty}
    output_amount: int = 1
    action_type: str = field(default="craft", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.node_id)
        if node is None:
            return {}

        # Tool durability check (cook uses cooking_tools; blacksmith has no tool)
        tool_type = ROLE_TOOL.get(self.agent.role.value, "")
        if tool_type:
            remaining = self.agent.consume_tool(tool_type, TOOL_DECAY)
            if remaining <= 0.0:
                self.agent.needs[NeedType.TOOL_NEED] = min(
                    1.0, self.agent.needs.get(NeedType.TOOL_NEED, 0.0) + TOOL_NEED_SPIKE
                )
                log.debug("Agent %s craft tool '%s' broken", self.agent.id, tool_type)
                return {}

        for good, qty in self.inputs.items():
            if node.stockpile.get(good, 0) < qty:
                log.debug("Craft failed — insufficient %s at %s", good, self.node_id)
                return {}
        # Consume inputs
        delta: dict[str, int] = {}
        for good, qty in self.inputs.items():
            node.stockpile[good] -= qty
            delta[good] = -qty
        node.stockpile[self.output_good] = node.stockpile.get(self.output_good, 0) + self.output_amount
        delta[self.output_good] = self.output_amount
        log.debug("Agent %s crafted %d %s", self.agent.id, self.output_amount, self.output_good)
        return {self.node_id: delta}


@dataclass
class ConsumeFoodAction:
    agent: Agent
    food_good: str
    node_id: str
    action_type: str = field(default="consume", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.node_id)
        if node is None:
            return {}
        delta: dict[str, int] = {}
        if node.stockpile.get(self.food_good, 0) > 0:
            node.stockpile[self.food_good] -= 1
            delta[self.food_good] = -1
        elif self.agent.inventory.get(self.food_good, 0) > 0:
            self.agent.inventory[self.food_good] -= 1
            delta[self.food_good] = -1
        else:
            return {}
        satisfy_need(self.agent, NeedType.HUNGER, FOOD_SATISFY)
        if self.food_good in ("fruit", "cooked_meal"):
            satisfy_need(self.agent, NeedType.FOOD_SATISFACTION, 0.5)
        return {self.node_id: delta} if delta else {}


@dataclass
class TradeAction:
    agent: Agent       # seller / initiator
    buyer: Agent
    item_out: str      # what agent gives
    item_in: str       # what agent receives
    qty_out: int
    qty_in: int
    action_type: str = field(default="trade", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        seller_inv = self.agent.inventory
        buyer_inv = self.buyer.inventory
        if seller_inv.get(self.item_out, 0) < self.qty_out:
            return {}
        if buyer_inv.get(self.item_in, 0) < self.qty_in:
            return {}
        seller_inv[self.item_out] -= self.qty_out
        seller_inv[self.item_in] = seller_inv.get(self.item_in, 0) + self.qty_in
        buyer_inv[self.item_in] -= self.qty_in
        buyer_inv[self.item_out] = buyer_inv.get(self.item_out, 0) + self.qty_out
        log.debug("Trade: %s gave %d %s for %d %s (with %s)",
                  self.agent.id, self.qty_out, self.item_out,
                  self.qty_in, self.item_in, self.buyer.id)
        return {"_trade": {"partner": self.buyer.id, "gave": (self.item_out, self.qty_out),
                           "got": (self.item_in, self.qty_in)}}


@dataclass
class TravelAction:
    agent: Agent
    target_node: str
    action_type: str = field(default="travel", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        if self.target_node not in world.nodes:
            return {}
        # Determine travel cost from edge (default 1 for internal hops)
        edge_cost = 1
        for edge in world.edges:
            if ((edge.u == self.agent.current_node and edge.v == self.target_node) or
                    (edge.v == self.agent.current_node and edge.u == self.target_node)):
                edge_cost = max(1, edge.travel_cost)
                break
        prev = self.agent.current_node
        world_ops.move_agent(world, self.agent.id, self.target_node)
        self.agent.travel_ticks_remaining = edge_cost - 1  # -1 because this tick counts
        log.debug("Agent %s: %s → %s (cost=%d)", self.agent.id, prev, self.target_node, edge_cost)
        return {"_travel": {"from": prev, "to": self.target_node, "cost": edge_cost}}


@dataclass
class RaidAction:
    raider: RaiderFaction
    target_node: str
    action_type: str = field(default="raid", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.target_node)
        if node is None:
            return {}
        # Exclude raider itself from defenders list
        defenders = [a for a in world_ops.agents_at(world, self.target_node)
                     if a.id != self.raider.id]
        result, loot, combat_info = raid_resolution(self.raider, defenders, node.stockpile)
        for good, qty in loot.items():
            self.raider.inventory[good] = self.raider.inventory.get(good, 0) + qty
        bus.publish(RaidAttempt(
            tick=world.tick,
            source="agent_society",
            severity=EventSeverity.MAJOR,
            target_node=self.target_node,
            result=result,
            loot=loot,
        ))
        # Spike safety need for all agents caught at the raided node
        for victim in world_ops.agents_at(world, self.target_node):
            victim.needs[NeedType.SAFETY] = min(1.0, victim.needs.get(NeedType.SAFETY, 0.0) + 0.4)
        log.info("Raid on %s: %s atk=%.1f def=%d loot=%s",
                 self.target_node, result, combat_info["attack"], combat_info["defense"], loot)
        delta = {g: -q for g, q in loot.items()}
        return {"_raid": {"result": result, "loot": loot,
                          "attack": combat_info["attack"],
                          "defense": combat_info["defense"],
                          "armory": combat_info["armory"]},
                self.target_node: delta}


@dataclass
class CollectFromNodeAction:
    """Merchant picks up goods from a node's stockpile into personal inventory."""
    agent: Agent
    node_id: str
    good: str
    qty: int
    action_type: str = field(default="collect", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.node_id)
        if node is None:
            return {}
        available = node.stockpile.get(self.good, 0)
        take = min(self.qty, available)
        if take <= 0:
            return {}
        node.stockpile[self.good] -= take
        self.agent.inventory[self.good] = self.agent.inventory.get(self.good, 0) + take
        log.debug("Collect: %s took %d %s from %s", self.agent.id, take, self.good, self.node_id)
        return {self.node_id: {self.good: -take}}


@dataclass
class DeliverToNodeAction:
    """Merchant deposits goods from inventory into a city node's stockpile."""
    agent: Agent
    deposit_node: str
    good: str
    qty: int
    action_type: str = field(default="deliver", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        have = self.agent.inventory.get(self.good, 0)
        if have <= 0:
            return {}
        node = world.nodes.get(self.deposit_node)
        if node is None:
            return {}
        actual = min(self.qty, have)
        self.agent.inventory[self.good] -= actual
        node.stockpile[self.good] = node.stockpile.get(self.good, 0) + actual
        log.debug("Deliver: %s → %d %s to %s", self.agent.id, actual, self.good, self.deposit_node)
        return {self.deposit_node: {self.good: actual}}


@dataclass
class NodeTransferAction:
    """Crafter (blacksmith/cook) pulls goods from an adjacent node into their own node."""
    agent: Agent
    source_node: str
    dest_node: str
    good: str
    qty: int
    action_type: str = field(default="restock", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        src = world.nodes.get(self.source_node)
        dst = world.nodes.get(self.dest_node)
        if not src or not dst:
            return {}
        available = src.stockpile.get(self.good, 0)
        take = min(self.qty, available)
        if take <= 0:
            return {}
        src.stockpile[self.good] -= take
        dst.stockpile[self.good] = dst.stockpile.get(self.good, 0) + take
        log.debug("Restock: %s pulled %d %s from %s to %s",
                  self.agent.id, take, self.good, self.source_node, self.dest_node)
        return {self.source_node: {self.good: -take}, self.dest_node: {self.good: take}}


@dataclass
class AcquireToolAction:
    """Producer picks up a replacement tool from a node stockpile and resets durability."""
    agent: Agent
    node_id: str
    tool_type: str
    action_type: str = field(default="acquire_tool", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.node_id)
        if node is None or node.stockpile.get(self.tool_type, 0) <= 0:
            return {}
        node.stockpile[self.tool_type] -= 1
        self.agent.tool_durability[self.tool_type] = 10.0
        satisfy_need(self.agent, NeedType.TOOL_NEED, 0.5)
        log.info("%s replaced %s from %s (durability reset)", self.agent.id, self.tool_type, self.node_id)
        return {self.node_id: {self.tool_type: -1}}


@dataclass
class BuyAction:
    """Gold를 지불하고 node stockpile에서 재화를 구입."""
    agent: Agent
    node_id: str
    good: str
    qty: int
    unit_price: float          # gold per unit (pre-computed)
    action_type: str = field(default="buy", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.node_id)
        if node is None:
            return {}
        available = node.stockpile.get(self.good, 0)
        affordable = int(self.agent.gold // self.unit_price) if self.unit_price > 0 else 0
        qty = min(self.qty, available, affordable)
        if qty <= 0:
            return {}
        cost = round(qty * self.unit_price)
        # 닫힌 gold 계: agent → node.gold
        self.agent.gold -= cost
        node.gold += cost
        node.stockpile[self.good] -= qty
        self.agent.inventory[self.good] = self.agent.inventory.get(self.good, 0) + qty
        log.debug("Buy: %s bought %d %s @ %.1f g/unit = %dg (node %s, pool→%d)",
                  self.agent.id, qty, self.good, self.unit_price, cost, self.node_id, node.gold)
        return {self.node_id: {self.good: -qty}, "_gold": -cost}


@dataclass
class SellAction:
    """재화를 node stockpile에 팔고 gold를 수취."""
    agent: Agent
    node_id: str
    good: str
    qty: int
    unit_price: float          # gold per unit (pre-computed)
    action_type: str = field(default="sell", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.node_id)
        if node is None:
            return {}
        have = self.agent.inventory.get(self.good, 0)
        qty = min(self.qty, have)
        if qty <= 0:
            return {}
        revenue = round(qty * self.unit_price)
        # node.gold가 부족하면 가능한 만큼만 지급
        actual_revenue = min(revenue, node.gold)
        if actual_revenue <= 0 and node.gold <= 0:
            return {}
        # 닫힌 gold 계: node.gold → agent
        node.gold -= actual_revenue
        self.agent.gold += actual_revenue
        self.agent.inventory[self.good] -= qty
        node.stockpile[self.good] = node.stockpile.get(self.good, 0) + qty
        log.debug("Sell: %s sold %d %s @ %.1f g/unit = %dg (node %s, pool→%d)",
                  self.agent.id, qty, self.good, self.unit_price, actual_revenue, self.node_id, node.gold)
        return {self.node_id: {self.good: qty}, "_gold": actual_revenue}


@dataclass
class AcquireWeaponAction:
    """Merchant buys a sword from the smithy when feeling unsafe."""
    agent: Agent
    source_node: str
    weapon_type: str = "sword"
    action_type: str = field(default="equip", init=False)

    def execute(self, world: World, bus: WorldEventBus) -> dict:
        node = world.nodes.get(self.source_node)
        if node is None or node.stockpile.get(self.weapon_type, 0) <= 0:
            return {}
        node.stockpile[self.weapon_type] -= 1
        self.agent.equipped_weapon = Item(
            type=self.weapon_type,
            tier=Tier.BASIC,
            durability=40.0,
            max_durability=50.0,
        )
        log.info("%s acquired %s from %s", self.agent.id, self.weapon_type, self.source_node)
        return {self.source_node: {self.weapon_type: -1}}
