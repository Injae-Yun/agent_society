# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**Agent-Society** is a Python 3.11+ RPG prototype: needs-driven agent society simulation + external event injection + LLM quest narration. M1–M3 are complete (world, quests, gold economy). M4+ (PlayerAgent, factions, endings) are planned in `PLAN.md`.

**Time unit**: 1 tick = 1 in-game hour. 24 ticks/day, 168 ticks/week, 720 ticks/season.

---

## Commands

```bash
pip install -e ".[dev]"                                        # setup

python scripts/generate_replay.py                              # generate HTML replay (default 2500t ≈ 104 days)
python scripts/generate_replay.py --ticks 500 --seed 1        # custom run
python -m agent_society --scenario configs/mvp_scenario.yaml  # headless run

pytest                        # all tests
pytest tests/unit             # unit only
pytest -k "raid"              # keyword filter

ruff check src/ && ruff format src/
mypy src/
```

---

## Architecture

Three systems share state **only** via `WorldSnapshot` (read-only proxy, not a deep copy) and `WorldEventBus` (pub/sub). Direct cross-system mutation is forbidden.

### Tick order (`simulation/driver.py`)

```
1. EventGenerator.tick(snapshot)      — catalog-driven WorldEvent publication
2. bus.drain(world)                   — apply events → world mutations
3. AgentSociety.tick(world)           — needs decay → action select → execute (ID-ascending)
4. bus.drain(world)                   — apply agent-triggered events (e.g. RaidAttempt)
5. QuestGenerator.tick(snapshot)      — every 168 ticks: urgent needs → LLM narration
6. PlayerInterface.tick(world)        — (M4, stub for now)
7. bus.drain(world)
8. expire old events, record tick, tick += 1
```

### Dependency direction (no cycles)

```
schema.py ← anyone (imports nothing)
config/*  ← anyone
economy/* → schema, config
events/*  → schema, config
world/*   → schema, config
agents/*  → schema, config, events, economy, world
quests/*  → schema, config, events, llm, world
simulation/* → all
```

### Write permissions

| Field | Writer |
|---|---|
| `node.stockpile`, `node.gold` | AgentSociety (via actions), event handlers |
| `edge.severed`, `edge.base_threat` | Event handlers only |
| `agent.current_node`, `agent.needs`, `agent.inventory`, `agent.gold` | AgentSociety |
| `raider.strength` | AgentSociety, event handlers |
| `world.active_events` | WorldEventBus |
| `world.tick` | SimulationDriver |

---

## Key Design Rules

- **`schema.py` is pure dataclasses** — no logic, no sibling imports. Never add methods beyond `__post_init__` helpers.
- **LLM only in `llm/` layer** — `QuestNarrator.narrate()` is the single LLM call site. Always use `MockNarrator` in tests.
- **Deterministic by seed** — each system holds its own `Random` instance. Never use global `random`.
- **Cascade depth = 3** — events published inside `bus.drain()` recurse at most 3 levels.
- **`WorldSnapshot` is a live proxy** — it reads directly from `World`; don't use it for mutation.

---

## World Model

```
          risky route (상단, 4 tiles)
City ────────────── ☠ Hideout ───────────────── Farmland
  └─── safe route (하단 U자, 10 tiles) ─────────┘
```

**Nodes**: `city` and `farm` are single logical nodes (consolidated from former sub-nodes). `raider.hideout` is a single node visualised as a 5-hex territory blob. 14 route tiles: `route.risky.1..4` (short, top) + `route.safe.1..10` (long U-shape, bottom).

**Affordances**:
- `city`: `trade, craft_weapons, craft_tools, cook, rest`
- `farm`: `trade, produce_wheat, produce_meat, produce_fruit, produce_ore`
- `raider.hideout`: `raider_spawn`
- route tiles: none (transit-only)

**Visual slots**: inside city/farm, each producer role occupies a specific neighbour hex of the big zone hex (see `ROLE_VISUAL_OFFSET` in `hex_map.py`). This is render-only — logically all city agents share the same `city` node stockpile.

**9 roles**: Farmer, Herder, Miner, Orchardist (1° producers, live at `farm`); Blacksmith, Cook (2°, live at `city`); Merchant (transporter, `city`↔`farm`); Raider (single faction, `strength` float, `raider.hideout`).

**4 needs**: `hunger` (grows ~0.06/t), `food_satisfaction` (grows ~0.02/t), `tool_need` (spikes on tool break), `safety` (decays 0.010/t — threat memory).

---

## Merchant Routing Rules

These are fragile and frequently break. Key invariants:

- **Merchants only trade** (`BuyAction`/`SellAction`) at `city` or `farm` — never at route midpoints.
- **Deliver/collect/weapon-buy** logic fires only when `agent.current_node == "city"` or `== "farm"` — never at route tiles (`cur_region == RegionType.CITY` is NOT a reliable check because route tiles have their own regions).
- **Route tiles** are transit-only. No scoring logic should trigger there except travel and eat.
- **Routing path**: city → risky.1..4 → farm (armed) **or** city → safe.1..10 → farm (unarmed). Entry/exit hops are city↔route and route↔farm; no intermediate hub.
- **Risky route threshold**: armed merchants use risky if `safety < 0.75`; unarmed if `safety < 0.15`.
- **`_TRADEABLE_GOODS`** for arbitrage = `("wheat", "meat", "fruit", "ore", "cooked_meal")`. Tools and weapons are excluded — they have dedicated deliver/collect logic.
- **Raider scope**: raids hit **route tiles only** (`AMBUSH_PROB` keyed on `route.risky.*` + hungry raider extension to `route.safe.*`). City and farm are never raid targets.

---

## Gold Economy

**Closed loop**: gold is created only by `ProduceAction` wages (`BASE_VALUE × PRODUCE_WAGE` per unit). All other transactions move existing gold.

| Transaction | Direction |
|---|---|
| `BuyAction` | agent.gold → node.gold |
| `SellAction` | node.gold → agent.gold |
| `AcquireToolAction` | agent.gold → node.gold (only if node has `trade` affordance) |
| `ConsumeFoodAction` from node stockpile | agent.gold → node.gold (only if node has `trade` affordance) |

**Price formula** (`economy/exchange.py`):
```
price = BASE_VALUE * clamp(1 + SCARCITY_K*(1 - stock/normal), 0.5, 3.0) * inflation_factor
inflation_factor = clamp(total_agent_gold / BASELINE_GOLD, 0.5, 3.0)
```

**`GoldTax` event** fires when total agent gold > `GOLD_TAX_THRESHOLD` (2000g), collecting 20% from all agents.

---

## Event System

**Catalog** (`events/catalog.py`): `EventTemplate` with condition λ, weight λ, cooldown ticks, and kwargs. `EventGenerator` evaluates every tick; fires probabilistically when condition is met and not on cooldown.

**Handlers** (`events/handlers.py`): registered via `register_all_handlers(bus)` — called in `AgentSociety.__init__`. Adding a new event type requires: new class in `types.py` → handler in `handlers.py` → `bus.subscribe(...)` → optionally a catalog entry.

---

## Quest System

`QuestGenerator.tick()` runs every 168 ticks. Flow:
```
agent.needs > URGENCY_THRESHOLD (0.7)
  → QuestIntent (intent.py) — typed by need pattern
  → merger.py deduplicates by (quest_type, target)
  → QuestNarrator.narrate() — LLM call (or MockNarrator)
  → QuestIntent.status: pending → active → completed/expired
```
Reward escalates with urgency × supporter count × ticks pending. Deadline = `issued_tick + 168`.

---

## LLM Backends

| Class | Location | Use |
|---|---|---|
| `MockNarrator` | `llm/mock_backend.py` | Tests (always) |
| `HuggingFaceNarrator` | `llm/hf_backend.py` | Local `google/gemma-4-E4B-it` via transformers |
| `OllamaNarrator` | `llm/ollama_backend.py` | Ollama server |

---

## Naming Conventions

| Kind | Convention |
|---|---|
| Modules/files | `snake_case` |
| Classes | `PascalCase` |
| Constants | `UPPER_SNAKE` |
| Node IDs | Single-word for zone hubs (`city`, `farm`); dotted for route tiles (`route.safe.1`, `route.risky.3`) and special (`raider.hideout`) |
| Enum values | `UPPER_SNAKE` — e.g. `Role.BLACKSMITH`, `NeedType.SAFETY` |
