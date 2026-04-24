# PLAN.md — Agent-Society 마일스톤

> 관련 문서: `ARCHITECTURE.md` (코드 경계), `society_and_map.md` (맵 설계),
> `docs/research/04_local_llm_hardware.md` (LLM 모델·VRAM)

---

## 비전 요약

**대항해시대류 시장 시뮬레이터 + 퀘스트 수행 게임.**
NPC 사회가 자율적으로 돌아가는 월드 안에서 플레이어가 1명의 Agent로 살아간다.
플레이어 목표: **돈 축적 / 명성 획득 / 엔딩 달성**.

---

## 마일스톤 현황

| 마일스톤 | 상태 | 요약 |
|---|---|---|
| M0 | ✅ 완료 | 선행 연구·아키텍처 설계 문서 |
| M1 | ✅ 완료 | tick loop 스켈레톤 + 모든 시스템 stub |
| **M2** | ✅ 완료 | Quest 시스템 + LLM 연결 |
| **M3** | ✅ 완료 | 화폐 + 시장 가격 시스템 |
| **M4** | ✅ 완료 | AdventurerAgent + Quest 효과 (자원 평형 자동화) |
| **M5** | ✅ 완료 | PlayerAgent + d20 주사위 + LLM 결과 서사 |
| **M6** | ✅ 완료 | 세력(Faction) + 명성·소문 전파 초기 틀 |
| **M7** | ✅ 완료 | 절차적 맵 생성 + Voronoi/biome/roads/lair + generate_world 통합 |
| M8 | 🔲 다음 | 엔딩 조건 + 게임 루프 완성 |
| M8 | 🔲 예정 | 엔딩 조건 + 게임 루프 완성 |

---

## M1 — 완료 (tick loop 스켈레톤)

**구현 완료 파일**:
- `schema.py`, `config/`, `world/`, `events/`, `agents/`, `economy/`, `simulation/`
- `llm/` — base Protocol, mock_backend, ollama_backend, hf_backend, prompts
- `player/` — interface Protocol (stub)
- `configs/mvp_scenario.yaml` — 52 agent, 12 node MVP 월드
- `tests/unit/` — 27 tests, all pass

---

## M2 — Quest 시스템 + LLM 연결

### 목표
agent needs 임계 초과 → QuestIntent 생성 → LLM 서사화 → 플레이어에게 제시.
7일(168 tick)마다 퀘스트 갱신. 이 단계에서 플레이어는 아직 "퀘스트를 읽는" 수준.

### 설계 원칙
- LLM은 **서사 생성기**일 뿐 — 퀘스트 로직(조건·보상·효과)은 코드가 결정한다.
- `QuestContext` = agent 상태의 구조화된 요약. LLM이 "왜 이 퀘스트인가"를 이해하는 입력.

### quest_type ↔ 발생 조건 매핑

| quest_type | 조건 | target |
|---|---|---|
| `bulk_delivery` | 특정 재화 scarcity > 0.6 AND 관련 needs 높은 agent ≥ 2명 | 부족 재화 종류 |
| `raider_suppress` | `safety` > 0.7인 agent ≥ 2명 OR raider.strength > 60 | raider faction |
| `road_restore` | `RoadCollapse` 이벤트 활성 AND 영향 받는 agent ≥ 1명 | 끊긴 edge |
| `escort` | risky route 사용 중인 agent AND safety 높음 | 목적지 node |

### 퀘스트 생명주기
```
issued (7일마다 생성)
  → pending   : 플레이어에게 제시됨
  → active    : 플레이어 수락
  → completed : 달성 조건 충족
  → expired   : 다음 갱신 시까지 미수락·미완료
```
deadline = 다음 갱신 tick (issued_tick + 168).

### QuestIntent 필드 (schema.py 추가)
```python
@dataclass
class QuestIntent:
    id: str
    quest_type: str          # bulk_delivery | raider_suppress | road_restore | escort
    target: str              # node/edge/faction id
    urgency: float           # 0.0 ~ 1.0
    supporters: list[str]    # 의뢰자 agent id 목록
    reward: dict[str, int]   # {"gold": 50, "wheat": 10} — M3 이전엔 재화만
    quest_text: str          # LLM 생성 서사
    status: str              # pending | active | completed | expired
    issued_tick: int
    deadline_tick: int
```

### 보상 공식
```
base_gold = BASE_REWARD[quest_type]
reward = base_gold * (1 + urgency) * (1 + 0.1 * len(supporters)) * (1 + 0.01 * ticks_pending)
```
M3 이전엔 gold 대신 재화로 지급.

### 구현 파일
| 파일 | 책임 |
|---|---|
| `quests/intent.py` | QuestIntent 생성 로직 (needs → intent 매핑) |
| `quests/merger.py` | 유사 intent 병합 (type+target 동일 or supporters 겹침) |
| `quests/reward.py` | 보상 에스컬레이션 공식 |
| `quests/generator.py` | `QuestGenerator.tick()` — 168 tick 주기 |
| `config/parameters.py` | `QUEST_REFRESH_INTERVAL = 7 * TICK_PER_DAY` |

### 테스트
- `tests/unit/test_quests.py` — intent 생성, merge 아이덴포턴스
- `tests/integration/test_quest_cycle.py` — 흉년 → needs 임계 → Quest 생성 e2e

---

## M2.5 — LLM 이벤트 선택 (M3에 편입)

### 설계 확정
- **가격** = 순수 공식 (stockpile → scarcity_factor). LLM 불필요.
- **이벤트 발생 원인** = 두 레이어:
  - 조건 기반(코드): 플레이어 행동 결과, 임계 초과 → 즉시 발동
  - 서사 기반(LLM): 7일마다 월드 맥락을 읽고 카탈로그에서 이벤트 선택

### LLM 이벤트 선택 입력/출력
```python
# 입력 (구조화된 월드 요약)
{
  "season": "Autumn", "week": 7,
  "stockpile_trend": {"wheat": "3주 감소", "ore": "안정"},
  "active_events": [],
  "raider_strength": 72,
  "available_events": ["drought", "harvest_failure", "raider_surge", ...]
}
# 출력 (JSON 1줄)
{"event": "drought", "intensity": 0.7, "narrative": "3주째 비가..."}
```

### 이벤트 카탈로그 확장 (현재 4개 → 15개)
각 이벤트에 `market_effect: dict[good, multiplier_delta]` 추가.

| 추가 이벤트 | 주요 market_effect |
|---|---|
| `Drought` | wheat +0.8, fruit +0.6 |
| `Flood` | wheat +0.5, road 일부 차단 |
| `MineCollapse` | ore +1.0, sword +0.5 |
| `TradeGlut` | 특정 재화 -0.4 |
| `Epidemic` | food needs ↑, travel ↓ |
| `RaidScare` | safety needs ↑ |
| `BumperCrop` | wheat -0.5, fruit -0.4 |
| `WeaponsDemand` | sword +0.8 |
| `RoadDeterioration` | travel_cost ↑ |
| `FamineThreat` | 전체 food +0.6 |

M3 가격 공식 구현 시 `market_effect` 가 multiplier로 연결됨.

---

## M3 — 화폐 + 시장 가격 시스템

### 목표
NPC 간 바터를 유지하되 **gold** 화폐 도입.
재화마다 node별 가격이 scarcity에 따라 실시간으로 변동하는 시장 구축.

### 설계

#### 화폐
- Agent에 `gold: int = 0` 필드 추가 (schema.py).
- 상인(Merchant)은 이동 시 재화를 구매하고 목적지에서 판매 → gold 차익.
- 퀘스트 보상을 gold로 지급 가능.

#### 가격 공식
```
price(node, good) = BASE_VALUE[good] * scarcity_factor(node, good)

scarcity_factor = 1 + SCARCITY_K * max(0, 1 - stockpile / NORMAL_STOCKPILE[good])
  → stockpile 풍부 시 ≈ 1.0 (기준가)
  → stockpile 고갈 시 최대 1 + SCARCITY_K (기본값 SCARCITY_K = 2.0)
```

#### NPC 상인 행동
- `Merchant.tick()`: 현재 node에서 가장 scarcity 높은 재화 매입
  → 목적지 node에서 판매. 차익이 travel_cost 이상일 때만 이동.
- 이 과정이 자연스러운 가격 균형(arbitrage)을 만들어냄.

#### 구현 파일
| 파일 | 변경 |
|---|---|
| `schema.py` | `Agent.gold: int = 0` 추가 |
| `config/balance.py` | `NORMAL_STOCKPILE`, `SCARCITY_K`, `BASE_VALUE` 정비 |
| `economy/exchange.py` | `price(world, node_id, good)` 함수 구현 |
| `agents/roles.py` | `Merchant` 행동 로직 (arbitrage 판단) |

---

## M4 — AdventurerAgent + Quest 효과 (완료)

### 목표
Quest 시스템을 "읽기만 하는 보드"에서 **자원 평형을 자동으로 유지하는 엔진**으로 전환.
NPC Adventurer가 pending quest를 소비하면서 raider 토벌 / 부족 재화 공급 / 도로 복구를 실행한다.

### 구현 요약
- `Role.ADVENTURER` + `AdventurerAgent(skill, combat_power, active_quest_id, quest_progress)`
- `QuestIntent`에 `taker_id`, `tier` (common | heroic) 추가
- `agents/adventurer.py.tick_adventurer()` — eat → progress → accept → idle 흐름
- `quests/effects.py.apply_completion()` — quest_type별 world mutation
  - `raider_suppress` → raider.strength −25, 전원 safety −0.4
  - `bulk_delivery` → city stockpile[target] +15
  - `road_restore` → severed edge 복구
  - `escort` → supporter safety −0.3
- `AgentSociety.set_quest_gen()` — driver가 tick 시작 시 wiring
- recorder에 `active_quest`, `quest_progress` 기록 / HTML 아이콘 📜⚒🏆

### 검증
3000-tick 시뮬에서 raider.strength 60→43→55 자체 평형, cycle당 2 quest 완료.
tests 40/40 통과.

### 🔲 Adventurer 고도화 (M5 이후 정리할 백로그)
- **Quest throughput 확장** — 현재 cycle(168t)당 2개 제한. refresh 주기 단축 혹은 adventurer 1명이 여러 quest 순차 처리
- **Quest 타입 다양화** — `WeaponsDemand`, `MineDelivery`, `Exploration` 등 intent 생성 패턴 확장 (M2.5 이벤트 카탈로그와 연동)
- **Adventurer 경제 sustainability** — reward vs GoldTax 손실 밸런스 (현재 gold 2~8g 수준 유지). 등급제 reward 고려
- **실제 이동** — 현재 Adventurer는 city 고정 추상 처리. `raider_suppress`면 hideout까지 가는 이동 포함
- **전투 메커니즘** — combat_power를 실제 raider 전투로 연결 (M5 Player FIGHT와 같이 설계)
- **Heroic tier 조건** — 현재 tier 필드만 존재. 실제 heroic quest 발생 조건 및 Player 전용 처리

---

## M5 — PlayerAgent (월드 내 행위자)

### 목표
플레이어가 NPC와 **같은 tick**에서 움직이는 1인 Agent.
Quest 처리는 M4 Adventurer와 **같은 경로**(`quests/effects.py`) 공유 — Player는 "입력 받는 특별한 Adventurer".

### 플레이어와 NPC의 차이
| 항목 | Adventurer NPC | Player |
|---|---|---|
| 행동 결정 | `tick_adventurer()` 자동 | 외부 `PlayerInterface` 입력 큐 |
| Quest tier | `common`만 수락 | `common` + `heroic` 수락 가능 |
| 추가 상태 | `skill`, `combat_power`, `active_quest_id`, `quest_progress` | 위 + `reputation`, `quest_log` |

### PlayerAgent 구조
```python
@dataclass
class PlayerAgent(AdventurerAgent):     # inherits quest fields
    reputation: dict[str, float] = field(default_factory=dict)   # faction_id → -100~100
    quest_log: list[str] = field(default_factory=list)           # 완료한 quest id 기록
    pending_action: PlayerAction | None = None                   # 다음 tick 처리할 입력
```

### 플레이어 행동 타입
```python
class PlayerActionType(Enum):
    MOVE          # target_node 지정 → travel
    BUY           # (good, qty) at current trade node
    SELL          # (good, qty)
    FIGHT         # raider.hideout에서 raider와 전투 → strength -=
    REST          # 1 tick 대기, hunger 소폭 회복
    ACCEPT_QUEST  # quest_id → 수락
    WORK_QUEST    # active quest progress (Adventurer와 동일 틱당 진행)
    COMPLETE_QUEST # progress ≥ 1.0 일 때 명시적 완료

@dataclass
class PlayerAction:
    type: PlayerActionType
    target_node: str | None = None
    good: str | None = None
    qty: int | None = None
    quest_id: str | None = None
```

### PlayerInterface
```python
class PlayerInterface(Protocol):
    def tick(self, world: World, player: PlayerAgent) -> PlayerAction | None: ...
```
- **M5 기본**: `ScriptedPlayer` — 액션 큐에서 순서대로 꺼냄 (헤드리스 시뮬용 / 테스트 용)
- **추후**: `CLIPlayer` — stdin 입력, `BrowserPlayer` — WebSocket (M7+)

### Player tick 흐름 (`tick_player()` in `agents/player.py`)
```
1. pending_action 없음:
   → PlayerInterface.tick() 호출 → 액션 수령
2. pending_action 있음:
   → 타입별 dispatch
      MOVE  → TravelAction
      BUY   → BuyAction  (BuyAction 기존 로직 재사용)
      SELL  → SellAction
      FIGHT → raider strength -= combat_power × 2; player safety 상승
      ACCEPT_QUEST → quest_gen.accept() + taker_id = player.id
      WORK_QUEST   → active quest progress 증가 (Adventurer와 동일 공식)
      COMPLETE_QUEST → apply_completion() + 보상 + quest_log 추가
      REST  → hunger -0.15, safety -0.05
3. pending_action 소비 후 None으로
```

### 전투 (FIGHT)
```
player_power = player.combat_power + equipped_weapon.durability × 0.5
raider_power = raider.strength × rng.uniform(0.8, 1.2)

if player_power > raider_power:
    raider.strength −= (player_power − raider_power) × 0.5      # 15~35
    player.needs[SAFETY] = max(0, safety − 0.3)                  # 영웅담
else:
    # 약탈당함
    loss = min(player.gold, int((raider_power − player_power)))
    player.gold −= loss; raider.inventory["gold_loot"] += loss   # 추상화
    equipped_weapon.durability = max(0, durability − 5)
```

### Heroic tier quest
- QuestGenerator가 `tier="heroic"` 플래그 설정 조건:
  - `urgency ≥ 0.9` AND `quest_type == "raider_suppress"` → heroic
  - 또는 M6 명성 상위 구간에서만 해금되는 전용 quest (추후)
- heroic 은 `_pick_best_quest`에서 adventurer 제외, **Player만 수락 가능**

### 구현 파일
| 파일 | 책임 |
|---|---|
| `schema.py` | `PlayerAgent` dataclass (AdventurerAgent 상속) |
| `agents/player.py` | `tick_player()` — Adventurer 로직을 입력-주도로 재사용 |
| `player/interface.py` | `PlayerInterface` Protocol + `ScriptedPlayer` 구현 |
| `player/actions.py` | `PlayerAction` enum + 타입별 dispatch |
| `simulation/driver.py` | `player` 슬롯 실제 활용 (기존에 stub만 있음) |
| `configs/mvp_scenario.yaml` | `player` 섹션 — 기본 1명, gold 100, 무기 없음 |

### 달성 조건 판정 (M4 `apply_completion`과 공유)
Adventurer와 동일한 경로. Player 전용 차이:
- `bulk_delivery`: Player가 실제로 SELL 한 qty 누적이 보상 목표 이상 → `WORK_QUEST` 대신 SELL action으로 자동 progress 계산
- `raider_suppress`: FIGHT action 반복으로 raider.strength 감소 기여. progress = Σ(이번 quest 동안 가한 damage) / required_damage
- `escort` / `road_restore`: MOVE 기반 방문 판정

### 보상 지급 (경제 순환)
- `QuestIntent.reward` 를 gold로 환산해 Player 지급 (Adventurer와 동일 공식)
- 기존 M4 는 새 gold 발행 — **M5 폴리시: 의뢰자 agent gold에서 차감**해 closed-loop 유지
- 의뢰자 pool < reward → partial reward + `quest_log`에 "deferred payment" 기록

### 테스트
- `tests/unit/test_player.py` — ScriptedPlayer가 BUY/SELL/ACCEPT_QUEST 실행, state 검증
- `tests/integration/test_player_quest_cycle.py` — quest 전체 사이클 e2e

---

## M6 — 세력(Faction) + 명성 시스템 (완료)

### 구현 요약
- `Faction` dataclass (id, name, home_region, hostile_by_default)
- 기본 3 factions (`civic`, `rural`, `raiders`) + role 기반 자동 매핑
- `Agent.faction_id`, `Agent.known_player_rep` 추가
- `factions/reputation.py`:
  - `apply_quest_completion_reputation()` — player.reputation 업데이트 + 의뢰자 직접 전파
  - `propagate_rumors()` — 같은 노드 agents 간 소문 (prob=0.08, decay=0.85)
  - `reputation_tier()` — hero/friend/neutral/wary/enemy 분류
- `AgentSociety`가 하루 1회 `propagate_rumors()` 호출
- `Player._complete_quest`에서 outcome_mult 반영해 reputation hook 호출
- recorder / HTML detail panel에 `reputation` (player canonical) / `known_player_rep` (NPC 소문) 표시

### 🔲 M6 후속 작업 (백로그)
- **가격 효과**: `node_price()`에 buyer reputation 반영 (hero 10% 할인 / enemy 거래 거부)
- **전투 태도**: enemy tier (≤ -60) agent가 player 선제공격 / 거래 거부
- **Heroic quest 조건 확장**: 명성 +60 이상에서 특정 tier quest 해금
- **명성 감소**: 퀘스트 expired / 상인 약탈 가담 등 -rep 이벤트

---

## M7 — 절차적 맵 생성 + 다중 도시·국가

### 목표
현재 hand-authored 2-hub 맵 → **seed 기반 절차적 생성**으로 전환.
Faction 상호작용이 의미 있으려면 지역 간 거리·지형·희소자원 분포가 **매 run마다 달라야** 한다 (리플레이성).

### 왜 절차적 생성인가
- **리플레이성**: 같은 game loop도 seed마다 다른 세계 → 플레이어가 반복 플레이 가치
- **faction 상호작용**: 2-hub 구조에선 세력 간 거리·접경 같은 개념이 없음. 여러 도시가 있어야 동맹·분쟁이 공간적으로 의미를 가짐
- **이벤트 다양성**: 자원 분포에 따라 quest 타입이 동적으로 조정됨 (ore가 먼 도시면 delivery quest 빈번 등)

### 생성 파이프라인
```
seed → MapGenerator
       ├─ 1. region layout   : Poisson-disk sampling으로 도시/팜/raider 거점 배치
       ├─ 2. terrain         : 노드별 biome 태그 (plains / hills / forest / wasteland)
       ├─ 3. resources       : biome 기반 stockpile 편향
       │                      (forest: wheat+fruit, hills: ore, coast: fish*…)
       ├─ 4. routes          : Delaunay 삼각분할 → MST + 일부 추가 edge (최소 연결 + 우회로)
       ├─ 5. faction assign  : 도시 별 faction (인접 도시끼리 같은 faction 확률 ↑)
       └─ 6. agent seeding   : role별 population 공식 + region 선호
```

### 구현 파일 (신규)
| 파일 | 책임 |
|---|---|
| `world/generation/layout.py` | Poisson-disk region centroid sampling |
| `world/generation/biomes.py` | biome enum + stockpile bias tables |
| `world/generation/routes.py` | Delaunay/MST 기반 edge 구성 |
| `world/generation/factions.py` | 도시-세력 매핑 (Voronoi / cluster) |
| `world/generation/generator.py` | 파이프라인 orchestrator (`generate_world(seed, size)`) |
| `configs/procedural.yaml` | generator 파라미터 (도시 수, biome 가중치 등) |

### 단계적 접근
1. **M7a — 스켈레톤**: 3~5 도시 랜덤 배치, 기존 role/faction 체계 재사용, hand-authored MVP와 동등한 동작
2. **M7b — biome/resource 편향**: 노드별 자원 편향 도입, merchant 경로가 다양화되는지 검증
3. **M7c — 국가(State) 개념**: Faction의 상위 레벨 (외교 상태: 전쟁·화평·교역). 접경 도시에서 관세·이동 제한
4. **M7d — agent 수 스케일**: 50 → 200+ (성능 검증 병행)

### 성능 목표
- LLM 없는 1 tick: < 50ms (200 agent 기준)
- QuestGenerator (LLM 포함): < 30s / 168 tick 주기
- 맵 생성: < 1초 (seed 기반 결정론)

### 리플레이성 메트릭 (검증용)
- 같은 seed → 동일 맵 (결정론)
- 다른 seed → 도시 수·배치·자원 분포 측정 다양성 (KL divergence ≥ 임계)
- faction 지배권 패턴이 seed마다 달라지는지 (도시 별 dominant faction diversity)

---

## M8 — 엔딩 조건 + 게임 루프 완성

### 엔딩 타입 (초안)

| 엔딩 | 조건 |
|---|---|
| **부호 엔딩** | gold > 10,000 AND 적어도 1개 세력 명성 +60 이상 |
| **영웅 엔딩** | 3개 이상 세력 명성 +60 이상 AND raider.strength < 10 유지 30일 |
| **패배 엔딩** | gold < 0 (파산) OR 전체 세력 명성 -60 이하 |
| **자유 엔딩** | 특정 조건 없이 플레이어가 /quit — 현재 상태 요약 출력 |

### 게임 루프 완성
- 시작 조건: PlayerAgent 초기 자원 설정 (gold 100, 무기 없음)
- 진행: 월드 자율 운행 + 플레이어 행동 + 퀘스트 갱신 (7일 주기)
- 종료: 엔딩 조건 감지 → 결과 화면 출력

---

## 설계 제약 (전 마일스톤 공통)

- **LLM은 서사 생성기만** — 퀘스트 조건·보상·효과는 반드시 코드가 결정
- **schema.py는 pure dataclass** — 로직 없음, 타 모듈 import 없음
- **결정론적 시드** — 각 시스템 고유 RNG. `random` 전역 사용 금지
- **플레이어도 같은 tick 안** — 별도 처리 페이즈 없음, `AgentSociety.tick()` 직후 실행
