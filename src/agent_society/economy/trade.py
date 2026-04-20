"""Trade execution logic."""

from __future__ import annotations

import logging

from agent_society.economy.exchange import fair_trade_qty
from agent_society.schema import Agent, World
from agent_society.world import world as world_ops

log = logging.getLogger(__name__)


def execute_trade(
    seller: Agent,
    buyer: Agent,
    item_out: str,
    qty_out: int,
    item_in: str,
    world: World,
) -> bool:
    """Attempt a barter trade between two agents at the same node.

    Returns True if trade succeeded.
    """
    if seller.current_node != buyer.current_node:
        log.debug("Trade failed — agents not at same node")
        return False

    world_stock = {
        good: world_ops.total_stock(world, good)
        for good in (item_out, item_in)
    }
    qty_in = fair_trade_qty(item_out, qty_out, item_in, world_stock)

    if seller.inventory.get(item_out, 0) < qty_out:
        return False
    if buyer.inventory.get(item_in, 0) < qty_in:
        return False

    seller.inventory[item_out] -= qty_out
    seller.inventory[item_in] = seller.inventory.get(item_in, 0) + qty_in
    buyer.inventory[item_in] -= qty_in
    buyer.inventory[item_out] = buyer.inventory.get(item_out, 0) + qty_out
    log.debug("Trade: %s gave %d %s, got %d %s", seller.id, qty_out, item_out, qty_in, item_in)
    return True
