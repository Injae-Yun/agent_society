# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**Agent-Society** is a Python 3.11+ RPG prototype combining:
- Needs-driven agent society simulation
- External event injection
- Local LLM (Ollama) quest narration

The project is currently in **pre-implementation / design phase**. No source code exists yet — only design documents. Implementation starts with M1 (world + needs tick skeleton).

---

## Commands

### Setup

```bash
pip install -e ".[dev]"
```

### Run simulation

```bash
python -m agent_society --scenario configs/mvp_scenario.yaml --ticks 1000
```

### Tests

```bash
pytest                          # all tests
pytest tests/unit               # unit only
pytest tests/integration        # integration only
pytest -k "raid"                # keyword filter
pytest --cov=agent_society      # with coverage
```

### Lint & type check

```bash
ruff check src/
ruff format src/
mypy src/
```

---

## Architecture

Three independent systems share state only through `WorldSnapshot` (read-only) and `WorldEventBus` (pub/sub). `SimulationDriver` orchestrates the tick loop.

### Tick order (per `simulation/driver.py`)

```
1. EventGenerator.tick(snapshot)   — publishes WorldEvents (conditionally)
2. bus.drain(world)                — applies events to world state
3. AgentSociety.tick(world)        — agents: needs decay → action select → execute
4. bus.drain(world)                — applies agent-triggered events
5. QuestGenerator.tick(snapshot)   — every 100 ticks; collects urgent needs → LLM narration
6. PlayerInterface.tick(world)     — processes player input, publishes events
7. bus.drain(world)
8. Expire old events, tick += 1
```

### Write permissions (strict — violations caught by unit tests)

| Field | Writer |
|---|---|
| `node.stockpile` | AgentSociety, event handlers |
| `edge.severed`, `edge.base_threat` | Event handlers |
| `agent.current_node`, `agent.needs`, `agent.inventory`, `agent.tools` | AgentSociety |
| `raider.strength` | AgentSociety, event handlers |
| `world.active_events` | WorldEventBus |
| `world.tick` | SimulationDriver |

### Key design constraints

- **LLM only in `llm/` layer** — `QuestNarrator.narrate()` is the single LLM call site. The simulation loop runs without LLM (use `MockNarrator` for tests).
- **`schema.py` is pure dataclasses** — no logic, no imports from sibling modules. All other modules import from it but it imports nothing.
- **Deterministic by seed** — each system holds its own seeded RNG. Never use global `random`. Agent tick order is agent ID ascending.
- **WorldSnapshot** is a read-only proxy over `World`, not a deep copy. Systems receive a snapshot for decisions; mutations happen through each system's own methods.
- **Cascade depth limit = 3** — events published inside `bus.drain()` are handled within the same drain call, but limited to 3 levels to prevent infinite loops.

### Dependency direction (no cycles allowed)

```
schema.py ← anyone; imports nothing
config/* ← anyone
economy/* → schema, config
events/types.py → schema
events/bus.py → schema, events/types
world/* → schema, config
llm/* → schema, config
agents/* → schema, config, events, economy, world
quests/* → schema, config, events, llm, world
player/* → schema, events, world, quests
simulation/* → all (top-level orchestrator)
```

---

## World Model

The map is a **linear 3-region graph** with dual routes:

```
City ──── safe route (30 tick, 10% threat) ──── Farmland
     ──── risky route (10 tick, 70% threat) via Raider Base
```

**9 agent roles**: Farmer, Herder, Miner, Orchardist (1° producers); Blacksmith, Cook (2°); Merchant (courier); Raider (single faction agent with `strength` float).

**4 universal needs**: `hunger`, `food_satisfaction`, `tool_need`, `safety`.

**Economy**: Barter-only with scarcity-based variable exchange ratios. `BASE_VALUE` table in `config/balance.py`.

---

## Quest System

- `QuestGenerator` refreshes every `QUEST_REFRESH_INTERVAL = 100` ticks.
- Collects needs above urgency threshold → creates `QuestIntent` structs → merges structurally-similar intents → calls `QuestNarrator.narrate()` only for new/changed quests.
- Reward escalates with urgency, coalition size, and ticks pending.
- Always use `MockNarrator` in tests (`llm/mock_backend.py`).

---

## Implementation Order (M1 first)

1. `schema.py` — all dataclasses
2. `config/parameters.py`, `config/balance.py` — constants
3. `world/world.py`, `world/builder.py` — world construction
4. `agents/needs.py`, `agents/actions.py`, `agents/selection.py` — basic tick
5. `events/bus.py`, `events/types.py` — event infrastructure
6. `simulation/driver.py` — tick loop skeleton
7. `tests/unit/test_world.py`, `tests/unit/test_needs.py` — smoke tests

M1 excludes LLM and Quest systems (those are M3+).

---

## Naming Conventions

| Kind | Convention | Example |
|---|---|---|
| Modules/files | snake_case | `agents/actions.py` |
| Classes | PascalCase | `AgentSociety`, `QuestIntent` |
| Functions/variables | snake_case | `tick_agent`, `current_node` |
| Constants | UPPER_SNAKE | `TICK_PER_DAY`, `BASE_VALUE` |
| Enum values | UPPER_SNAKE | `Role.BLACKSMITH` |
| Node IDs | `region.specific` | `city.smithy`, `farmland.grain_field` |
