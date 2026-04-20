# Folder Structure (v0.1)

> Python 패키지 레이아웃과 파일별 책임.
> 구조는 `ARCHITECTURE.md`의 시스템 분할을 그대로 반영.

---

## 0. 원칙

1. **src/ 레이아웃**: 현대적 Python 표준. import 경로 혼란 방지
2. **시스템별 서브패키지**: Agent Society / Event / Quest / LLM 등이 각자 디렉터리
3. **schema는 중앙집중**: `schema.py` 하나에 핵심 dataclass 모음. 순환 import 방지
4. **config는 분리**: 파라미터 상수와 balance 테이블을 코드에서 분리 (YAML 로드)
5. **LLM 백엔드 추상화**: `llm/` 하위에 Protocol 정의, 구현체 교체 가능

---

## 1. 최상위 레이아웃

```
agent-society/
├── README.md
├── ARCHITECTURE.md
├── PLAN.md                          # 마일스톤 (추후 작성)
├── pyproject.toml                   # 의존성·빌드 설정
├── ruff.toml                        # 린트 설정
├── .gitignore
│
├── docs/
│   ├── research/                    # (기존) 선행 연구
│   │   ├── 00_overview.md
│   │   ├── 01_agent_society.md
│   │   ├── 02_quest_generation.md
│   │   ├── 03_event_generator.md
│   │   ├── 04_local_llm_hardware.md
│   │   └── references.md
│   └── design/
│       ├── society_and_map.md       # (기존) 직업·맵·경제 설계
│       └── folder_structure.md      # (본 문서)
│
├── src/
│   └── agent_society/               # 메인 패키지
│       ├── __init__.py
│       ├── __main__.py              # `python -m agent_society` 진입점
│       ├── schema.py                # 핵심 dataclass (Agent, Node, Edge, World, Item)
│       │
│       ├── world/                   # 월드 상태 관리
│       │   ├── __init__.py
│       │   ├── world.py             # World 클래스, 인덱스 갱신
│       │   ├── snapshot.py          # WorldSnapshot (read-only view)
│       │   └── builder.py           # 시나리오 → World 인스턴스
│       │
│       ├── agents/                  # Agent Society 시스템
│       │   ├── __init__.py
│       │   ├── society.py           # AgentSociety (tick orchestrator)
│       │   ├── needs.py             # Need 타입·decay 규칙
│       │   ├── actions.py           # Action 정의·실행
│       │   ├── selection.py         # utility AI (행동 선택)
│       │   ├── roles.py             # 8개 일반 역할 (Farmer, Herder, ...)
│       │   └── raider.py            # RaiderFaction 특수 처리
│       │
│       ├── events/                  # Event Generator + Bus
│       │   ├── __init__.py
│       │   ├── bus.py               # WorldEventBus (pub/sub)
│       │   ├── types.py             # WorldEvent 계층 (dataclass)
│       │   ├── generator.py         # EventGenerator
│       │   ├── catalog.py           # 이벤트 카탈로그 (조건·가중치·쿨다운)
│       │   └── handlers.py          # 이벤트 → World 상태 변경 핸들러
│       │
│       ├── quests/                  # Quest Generator
│       │   ├── __init__.py
│       │   ├── generator.py         # QuestGenerator (tick, refresh)
│       │   ├── intent.py            # QuestIntent (구조화 퀘스트)
│       │   ├── merger.py            # 유사도·병합 로직
│       │   └── reward.py            # 보상 에스컬레이션
│       │
│       ├── economy/                 # 경제·거래
│       │   ├── __init__.py
│       │   ├── goods.py             # Good 타입, BASE_VALUE 테이블
│       │   ├── exchange.py          # 교환 비율·scarcity
│       │   └── trade.py             # 거래 실행 로직
│       │
│       ├── llm/                     # LLM 백엔드 추상화
│       │   ├── __init__.py
│       │   ├── base.py              # QuestNarrator Protocol
│       │   ├── ollama_backend.py    # Ollama 구현체
│       │   ├── mock_backend.py      # 테스트·fallback 용
│       │   └── prompts.py           # 프롬프트 템플릿
│       │
│       ├── player/                  # 플레이어 인터페이스
│       │   ├── __init__.py
│       │   ├── interface.py         # PlayerInterface Protocol
│       │   └── cli.py               # CLI 구현 (MVP)
│       │
│       ├── simulation/              # tick loop·driver
│       │   ├── __init__.py
│       │   ├── driver.py            # SimulationDriver
│       │   └── clock.py             # tick·시간 단위 변환
│       │
│       └── config/                  # 파라미터·상수
│           ├── __init__.py
│           ├── parameters.py        # 시뮬 상수 (TICK_PER_DAY 등)
│           └── balance.py           # 밸런싱 수치 (BASE_VALUE 외)
│
├── configs/                         # 외부 시나리오 YAML
│   ├── mvp_scenario.yaml            # 기본 MVP 월드 정의
│   └── test_scenarios/
│       ├── famine.yaml
│       ├── raider_surge.yaml
│       └── road_blockade.yaml
│
├── tests/
│   ├── conftest.py                  # pytest fixtures
│   ├── unit/
│   │   ├── test_world.py
│   │   ├── test_needs.py
│   │   ├── test_actions.py
│   │   ├── test_events.py
│   │   ├── test_quests.py
│   │   ├── test_exchange.py
│   │   └── test_merger.py
│   ├── integration/
│   │   ├── test_tick_loop.py
│   │   ├── test_full_day.py
│   │   └── test_raid_resolution.py
│   ├── scenarios/
│   │   └── test_famine_scenario.py
│   └── fixtures/
│       └── mini_world.py            # 테스트용 축소 월드
│
└── scripts/
    ├── run_sim.py                   # 헤드리스 시뮬 실행
    ├── replay.py                    # 저장된 시드·입력 재생
    └── quest_inspect.py             # 활성 Quest 확인 도구
```

---

## 2. 파일별 책임 상세

### 2.1 `schema.py` (중앙집중 데이터 모델)

`Role`, `RegionType`, `Tier`, `Node`, `Edge`, `Item`, `Agent`, `World` 등.
순환 import 방지를 위해 **오로지 dataclass 정의**만. 로직은 넣지 않는다.

### 2.2 `world/world.py`

- `World` 인스턴스 메서드: `add_agent`, `move_agent`, `apply_event` 등
- 파생 인덱스(`agents_by_node`) 자동 갱신

### 2.3 `world/snapshot.py`

- `WorldSnapshot` — 읽기 전용 뷰
- World 객체를 참조하되 쓰기 메서드는 노출 X

### 2.4 `world/builder.py`

```python
def build_world_from_yaml(path: Path) -> World: ...
def build_mvp_world() -> World: ...   # 코드 기반 기본 MVP 월드
```

### 2.5 `agents/society.py`

- `AgentSociety.tick(world)`
- 이벤트 핸들러 등록 (`handlers.py`에서 import)

### 2.6 `agents/needs.py`

- `NeedType` enum: `HUNGER`, `FOOD_SATISFACTION`, `TOOL_NEED`, `SAFETY`
- `decay_needs(agent, dt)` 함수
- `need_urgency(agent)` — Quest 트리거 임계 계산

### 2.7 `agents/actions.py`

각 행동이 dataclass + `execute(world, bus)`:
- `ProduceAction(producer, node, good)`
- `CraftAction(crafter, output_good, inputs)`
- `ConsumeFoodAction(agent, food_item)`
- `TradeAction(seller, buyer, item_out, item_in, ratio)`
- `TravelAction(agent, route)`
- `RaidAction(raider, target_node)`

### 2.8 `agents/selection.py`

```python
def select_action(agent: Agent, snapshot: WorldSnapshot) -> Action:
    """각 후보 행동의 need 해소 점수 비교 → 최대 점수 선택."""
```

Utility AI 구현. LLM 미사용.

### 2.9 `agents/roles.py`

```python
class Farmer:
    primary_good = "wheat"
    required_tools = ["plow", "sickle"]
    available_actions = [ProduceAction, ConsumeFoodAction, TradeAction]
    
class Herder: ...
class Miner: ...
class Orchardist: ...
class Blacksmith: ...
class Cook: ...
class Merchant: ...
```

**주의**: MVP는 Role을 **데이터 클래스(카탈로그)로 취급**. 각 Role이 어떤
Action을 할 수 있는지 정의. Agent 본체는 `schema.Agent` 하나로 충분.

### 2.10 `agents/raider.py`

Raider는 특이행동(strength, 습격 판정)이 있으므로 별도 파일.

### 2.11 `events/bus.py`

```python
class WorldEventBus:
    def publish(self, event: WorldEvent): ...
    def subscribe(self, event_type, handler, priority=0): ...
    def drain(self, world) -> List[WorldEvent]: ...
```

### 2.12 `events/types.py`

WorldEvent 하위 dataclass 전체 (ARCHITECTURE §3.1 참조).

### 2.13 `events/generator.py`

```python
class EventGenerator:
    def tick(self, snapshot): 
        for template in self.catalog:
            if template.condition(snapshot) and self.pacing_ok(template):
                self.bus.publish(template.instantiate(snapshot, self.rng))
```

### 2.14 `events/catalog.py`

```python
CATALOG = [
    EventTemplate(
        name="harvest_failure",
        event_cls=HarvestFailure,
        condition=lambda snap: snap.season_tick > SOME_VALUE,
        weight=lambda snap: 1.0,
        cooldown=3 * TICK_PER_YEAR,
    ),
    # ...
]
```

### 2.15 `events/handlers.py`

이벤트별 World 상태 갱신 로직. subscribe 시 bus에 등록.

### 2.16 `quests/generator.py`

```python
class QuestGenerator:
    REFRESH_INTERVAL = 100
    def tick(self, snapshot): ...
    def refresh(self, snapshot): ...
    def find_similar(self, intent): ...
```

### 2.17 `quests/intent.py`

```python
@dataclass
class QuestIntent:
    id: str
    quest_type: str        # "road_restore", "raider_suppress", ...
    target: Any            # Edge id, Node id, good type
    supporters: List[AgentId]
    urgency: float
    ticks_pending: int
    narrative: Optional[str] = None  # LLM 생성 후 채워짐
```

### 2.18 `quests/merger.py`

```python
def similarity(a: QuestIntent, b: QuestIntent) -> float: ...
def merge(a: QuestIntent, b: QuestIntent) -> QuestIntent: ...
```

### 2.19 `economy/exchange.py`

```python
def exchange_rate(a: str, b: str, world_stock: Dict[str, int]) -> float: ...
```

### 2.20 `llm/base.py`

```python
from typing import Protocol

class QuestNarrator(Protocol):
    def narrate(self, intent: QuestIntent, context: QuestContext) -> str: ...
```

### 2.21 `llm/ollama_backend.py`

Ollama HTTP/CLI 호출 구현.

### 2.22 `llm/mock_backend.py`

```python
class MockNarrator:
    def narrate(self, intent, context):
        return f"[MOCK] {intent.quest_type} @ {intent.target}"
```

### 2.23 `llm/prompts.py`

프롬프트 템플릿. Few-shot 예제 포함.

### 2.24 `simulation/driver.py`

`SimulationDriver` — `ARCHITECTURE.md §4` tick loop 구현.

### 2.25 `config/parameters.py`

```python
TICK_PER_DAY = 144
TICK_PER_YEAR = TICK_PER_DAY * 360
QUEST_REFRESH_INTERVAL = 100
MAX_CASCADE_DEPTH = 3
DEFAULT_SEED = 42
```

### 2.26 `config/balance.py`

```python
BASE_VALUE = {"wheat": 1.0, "meat": 2.0, ...}
WEAPON_POWER = {"sword": 10, "bow": 7, ...}
RAID_RATE = 0.4
DESTRUCTION_FACTOR = 0.15
```

---

## 3. `pyproject.toml` 스켈레톤

```toml
[project]
name = "agent-society"
version = "0.1.0"
description = "Agent-based RPG prototype with LLM-narrated quests"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
    "httpx>=0.27",       # Ollama HTTP
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "hypothesis>=6.100",
    "ruff>=0.6",
    "mypy>=1.10",
]

[project.scripts]
agent-society = "agent_society.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]
```

---

## 4. `configs/mvp_scenario.yaml` 예시

```yaml
nodes:
  - id: city.market
    name: City Market
    region: city
    affordances: [trade]
  - id: city.smithy
    name: Smithy
    region: city
    affordances: [craft_weapons, craft_tools]
  - id: farmland.grain_field
    name: Grain Field
    region: farmland
    affordances: [produce_wheat]
  - id: raider_base.hideout
    name: Raider Hideout
    region: raider_base
    affordances: [raider_spawn]
  # ...

edges:
  - u: city.market
    v: farmland.hub
    variant: safe_route
    travel_cost: 30
    base_threat: 0.10
    capacity: 2
  - u: city.market
    v: farmland.hub
    variant: risky_route
    travel_cost: 10
    base_threat: 0.70
    capacity: 2

agents:
  - id: alice
    name: Alice
    role: merchant
    home_node: city.market
    inventory: {wheat: 5, meat: 3}
    equipped_weapon: {type: sword, durability: 40, max_durability: 50}
  - id: raiders
    name: Raider Band
    role: raider
    home_node: raider_base.hideout
    strength: 30.0
  # ...

initial_events: []
seed: 42
```

---

## 5. 테스트 구조

### 5.1 `tests/conftest.py`

공통 fixture:
- `mini_world` — 3 agent, 2 node 축소 월드
- `mvp_world` — MVP 시나리오 로드
- `mock_bus` — 테스트용 WorldEventBus
- `mock_narrator` — MockNarrator 인스턴스

### 5.2 실행

```bash
pytest                    # 전체
pytest tests/unit         # 단위만
pytest -k "raid"          # 키워드 매칭
pytest --cov=agent_society
```

---

## 6. 진입점

### 6.1 CLI 실행

```bash
python -m agent_society --scenario configs/mvp_scenario.yaml --ticks 1000
```

### 6.2 `scripts/run_sim.py`

```python
from agent_society.world.builder import build_world_from_yaml
from agent_society.simulation.driver import SimulationDriver

def main():
    world = build_world_from_yaml("configs/mvp_scenario.yaml")
    driver = SimulationDriver(world)
    for _ in range(1000):
        driver.world_tick()
    print(driver.summary())
```

---

## 7. 명명 규칙

| 종류 | 규칙 | 예 |
|---|---|---|
| 모듈·파일 | snake_case | `agents/actions.py` |
| 클래스 | PascalCase | `AgentSociety`, `QuestIntent` |
| 함수·변수 | snake_case | `tick_agent`, `current_node` |
| 상수 | UPPER_SNAKE | `TICK_PER_DAY`, `BASE_VALUE` |
| Enum 값 | UPPER_SNAKE | `Role.BLACKSMITH` |
| Protocol | `*Protocol` 또는 역할명 | `QuestNarrator`, `PlayerInterface` |
| ID 문자열 | `region.specific` | `city.smithy`, `farmland.grain_field` |

---

## 8. 의존성 방향 (순환 금지)

```
schema.py           ← 누구나 import 가능, 아무도 import 하지 않음
config/*            ← 누구나 import 가능
economy/*           ← schema, config 만 의존
events/types.py     ← schema 만 의존
events/bus.py       ← schema, events/types 의존
world/*             ← schema, config 의존
llm/*               ← schema, config 의존
agents/*            ← schema, config, events, economy, world 의존
quests/*            ← schema, config, events, llm, world 의존
player/*            ← schema, events, world, quests 의존
simulation/*        ← 모든 상위 모듈 의존 (최상위 orchestrator)
```

순환 import 감지: `python -m pyflakes src/` 혹은 ruff로 감지.

---

## 9. 첫 구현 순서 (M1 범위)

`PLAN.md`에서 정교화할 예정이지만, 구조 기준 착수 순서:

1. `schema.py` — 모든 dataclass
2. `config/parameters.py`, `config/balance.py` — 상수
3. `world/world.py`, `world/builder.py` — 월드 구축
4. `agents/needs.py`, `agents/actions.py`, `agents/selection.py` — 기본 tick
5. `events/bus.py`, `events/types.py` — 이벤트 인프라
6. `simulation/driver.py` — 빈 tick loop
7. `tests/unit/test_world.py`, `test_needs.py` — 스모크 테스트

이 단계까지가 **M1 (Milestone 1): 월드+needs tick 스켈레톤**. LLM·Quest는 M3+.
