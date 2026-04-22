"""SimulationRecorder — per-tick state + action capture for HTML replay."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from agent_society.config.balance import WEAPON_POWER as WEAPON_POWER_TABLE
from agent_society.schema import AdventurerAgent, NeedType, RaiderFaction, World
from agent_society.simulation.clock import tick_to_season


@dataclass
class ActionRecord:
    agent_id: str
    agent_name: str
    role: str
    action_type: str           # produce|craft|trade|travel|consume|raid|idle
    details: dict              # action-specific payload
    node_id: str               # node where action happened
    resource_delta: dict       # {node_id: {good: delta}} from execute() return


@dataclass
class AgentState:
    node: str
    needs: dict[str, float]        # {need_type: value}
    tool_durability: dict[str, float]
    inventory_total: int           # total non-internal item count
    inventory: dict[str, int]      # {good: qty} — full breakdown
    travel_ticks_remaining: int    # >0 = in transit
    gold: int = 0
    strength: float | None = None  # RaiderFaction only
    weapon: str | None = None      # equipped weapon type, or None if unarmed
    weapon_power: int | None = None  # combat value of equipped weapon (for display)
    active_quest: str | None = None  # AdventurerAgent/Player: currently-held quest id
    quest_progress: float | None = None  # 0.0~1.0


@dataclass
class QuestRecord:
    id: str
    quest_type: str
    target: str
    urgency: float
    status: str
    supporter_count: int
    reward: dict[str, int]
    quest_text: str
    issued_tick: int
    deadline_tick: int


@dataclass
class TickRecord:
    tick: int
    season: str
    node_stockpiles: dict[str, dict[str, int]]   # {node_id: {good: qty}}
    agent_states: dict[str, AgentState]           # {agent_id: AgentState}
    actions: list[ActionRecord]
    events: list[str]                             # WorldEvent class names
    quests: list[QuestRecord] = field(default_factory=list)


class SimulationRecorder:
    def __init__(self) -> None:
        self.records: list[TickRecord] = []
        # Static metadata (written once)
        self.meta: dict = {}

    def capture_meta(self, world: World) -> None:
        """Call once before simulation starts to record node/edge layout."""
        self.meta = {
            "nodes": {
                nid: {
                    "name": n.name,
                    "region": n.region.value,
                    "hex_q": n.hex_q,
                    "hex_r": n.hex_r,
                    "cluster_id": n.cluster_id,
                }
                for nid, n in world.nodes.items()
            },
            "edges": [
                {
                    "u": e.u, "v": e.v,
                    "travel_cost": e.travel_cost,
                    "base_threat": e.base_threat,
                }
                for e in world.edges
            ],
            "agents": {
                aid: {"name": a.name, "role": a.role.value}
                for aid, a in world.agents.items()
            },
        }

    def record_tick(
        self,
        world: World,
        actions: list[tuple[str, object]],   # [(agent_id, action_obj)]
        quest_gen: object | None = None,
    ) -> None:
        """Snapshot world state and record actions for this tick."""
        # Node stockpiles (exclude internal markers)
        stockpiles: dict[str, dict[str, int]] = {}
        for nid, node in world.nodes.items():
            stockpiles[nid] = {k: v for k, v in node.stockpile.items() if not k.startswith("_")}

        # Agent states
        agent_states: dict[str, AgentState] = {}
        for aid, agent in world.agents.items():
            inv = {k: v for k, v in agent.inventory.items() if not k.startswith("_") and v > 0}
            inv_total = sum(inv.values())
            weapon = None
            weapon_power = None
            if agent.equipped_weapon and agent.equipped_weapon.is_usable():
                weapon = agent.equipped_weapon.type
                weapon_power = WEAPON_POWER_TABLE.get(weapon, 0)
            active_quest = None
            quest_progress = None
            if isinstance(agent, AdventurerAgent):
                active_quest = agent.active_quest_id
                quest_progress = round(agent.quest_progress, 2) if agent.active_quest_id else None
            agent_states[aid] = AgentState(
                node=agent.current_node,
                needs={nt.value: round(v, 3) for nt, v in agent.needs.items()},
                tool_durability={k: round(v, 3) for k, v in agent.tool_durability.items()},
                inventory_total=inv_total,
                inventory=inv,
                travel_ticks_remaining=agent.travel_ticks_remaining,
                gold=agent.gold,
                strength=round(agent.strength, 1) if isinstance(agent, RaiderFaction) else None,
                weapon=weapon,
                weapon_power=weapon_power,
                active_quest=active_quest,
                quest_progress=quest_progress,
            )

        # Actions
        action_records: list[ActionRecord] = []
        for agent_id, action in actions:
            agent = world.agents.get(agent_id)
            if agent is None:
                continue
            action_type = getattr(action, "action_type", "idle")
            # Extract details from action attributes
            details = _extract_details(action)
            # resource_delta is stored on action after execute() (we read it from _last_delta)
            delta = getattr(action, "_last_delta", {})
            action_records.append(ActionRecord(
                agent_id=agent_id,
                agent_name=agent.name,
                role=agent.role.value,
                action_type=action_type,
                details=details,
                node_id=agent.current_node,
                resource_delta=delta,
            ))

        # Events
        event_names = [type(e).__name__ for e in world.active_events]

        # Quests
        quest_records: list[QuestRecord] = []
        if quest_gen is not None:
            for q in getattr(quest_gen, "active_quests", []):
                quest_records.append(QuestRecord(
                    id=q.id,
                    quest_type=q.quest_type,
                    target=q.target,
                    urgency=q.urgency,
                    status=q.status,
                    supporter_count=len(q.supporters),
                    reward=q.reward,
                    quest_text=q.quest_text,
                    issued_tick=q.issued_tick,
                    deadline_tick=q.deadline_tick,
                ))

        self.records.append(TickRecord(
            tick=world.tick,
            season=tick_to_season(world.tick),
            node_stockpiles=stockpiles,
            agent_states=agent_states,
            actions=action_records,
            events=event_names,
            quests=quest_records,
        ))

    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "ticks": [_tick_to_dict(r) for r in self.records],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_details(action: object) -> dict:
    details: dict = {}
    for attr in ("good", "output_good", "inputs", "item_out", "item_in",
                 "qty_out", "qty_in", "target_node", "amount", "output_amount",
                 "node_id", "deposit_node", "qty", "unit_price",
                 "source_node", "weapon_type", "tool_type"):
        val = getattr(action, attr, None)
        if val is not None:
            details[attr] = val
    buyer = getattr(action, "buyer", None)
    if buyer is not None:
        details["buyer_id"] = buyer.id
        details["buyer_name"] = buyer.name
    return details


def _tick_to_dict(r: TickRecord) -> dict:
    return {
        "t": r.tick,
        "s": r.season,
        "ns": r.node_stockpiles,
        "as": {aid: {
            "n": s.node,
            "needs": s.needs,
            "td": s.tool_durability,
            "inv": s.inventory_total,
            "items": s.inventory,
            "tr": s.travel_ticks_remaining,
            "gold": s.gold,
            "str": s.strength,
            "wpn": s.weapon,
            "wp": s.weapon_power,
            "aq": s.active_quest,
            "qp": s.quest_progress,
        } for aid, s in r.agent_states.items()},
        "ac": [{
            "id": a.agent_id,
            "nm": a.agent_name,
            "r": a.role,
            "t": a.action_type,
            "d": a.details,
            "nd": a.node_id,
            "rd": a.resource_delta,
        } for a in r.actions],
        "ev": r.events,
        "qx": [{
            "id": q.id,
            "qt": q.quest_type,
            "tg": q.target,
            "ug": q.urgency,
            "st": q.status,
            "sc": q.supporter_count,
            "rw": q.reward,
            "tx": q.quest_text,
            "it": q.issued_tick,
            "dt": q.deadline_tick,
        } for q in r.quests],
    }
