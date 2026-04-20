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
| **M4** | 🔲 다음 | PlayerAgent (월드 내 행위자) |
| M5 | 🔲 예정 | 플레이어 ↔ Quest 상호작용 루프 |
| M6 | 🔲 예정 | 세력(Faction) + 명성 시스템 |
| M7 | 🔲 예정 | 맵 확장 (다중 도시·국가) |
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

## M4 — PlayerAgent (월드 내 행위자)

### 목표
플레이어가 NPC와 **같은 tick** 안에서 움직이는 1인 Agent.
NPC와 동일한 물리 규칙(이동 비용, 위협, 재화 거래) 적용.

### 플레이어와 NPC의 차이
| 항목 | NPC | 플레이어 |
|---|---|---|
| 행동 결정 | `AgentSociety.tick()` 자동 결정 | 입력으로 받음 |
| 목표 | needs 충족 | gold 축적 / 명성 / 엔딩 |
| 추가 상태 | 없음 | `gold`, `reputation`, `quest_log` |

### PlayerAgent 구조
```python
@dataclass
class PlayerAgent(Agent):
    gold: int = 0
    reputation: dict[str, float] = field(default_factory=dict)  # faction_id → -100~100
    quest_log: list[str] = field(default_factory=list)           # 완료한 quest id
    pending_action: PlayerAction | None = None
```

### 플레이어 행동 타입
```python
class PlayerAction(Enum):
    MOVE       # destination node 지정 → Agent.travel_destination 설정
    BUY        # (good, qty) → gold 차감, inventory 증가
    SELL       # (good, qty) → gold 증가, inventory 차감
    FIGHT      # 현재 node의 raider와 전투 → raider.strength 감소
    REST       # 1 tick 대기
    ACCEPT_QUEST  # quest_id → status = active
```

### 전투 해소
```
outcome = player_power - raider.strength * random(0.8, 1.2)
  player_power = 10 + equipped_weapon.durability * 5  (무기 있으면 강함)
  outcome > 0  → raider.strength -= 15~30, 플레이어 안전
  outcome <= 0 → 플레이어 gold 일부 손실 (약탈)
```

### tick 컨트롤
플레이어는 게임 속도를 선택할 수 있다 (실시간 처리 속도, 게임 로직 변경 없음):
- `PAUSED` — tick 진행 중단, 플레이어 명령 대기
- `1x` — 표준 속도
- `4x` / `16x` — 가속 (tick_interval 단축)

### 구현 파일
| 파일 | 책임 |
|---|---|
| `schema.py` | `PlayerAgent` dataclass 추가 |
| `player/actions.py` | `PlayerAction` enum + 각 행동의 WorldEvent 발행 로직 |
| `player/cli.py` | CLI 입력 → PlayerAction 변환, tick 컨트롤 |
| `simulation/driver.py` | `PlayerAgent.tick()` 분기 처리 |

---

## M5 — 플레이어 ↔ Quest 상호작용 루프

### 목표
퀘스트 수락 → 플레이어 행동 → 달성 판정 → 보상 지급 → 월드 변화.
처음으로 "게임"이 된다.

### 달성 조건 판정

| quest_type | 달성 조건 |
|---|---|
| `bulk_delivery` | 플레이어가 target node에 지정 재화 qty 이상 SELL |
| `raider_suppress` | 플레이어 FIGHT 후 raider.strength < 30 |
| `road_restore` | 플레이어가 끊긴 edge 양 끝 node를 방문 (수리 재화 지참) |
| `escort` | 플레이어와 target agent가 같은 tick에 목적지 도착 |

### 보상 지급
- `QuestIntent.reward` 에 정의된 gold + 재화를 PlayerAgent에 지급.
- 보상은 의뢰자 agent의 gold/inventory에서 차감 (경제 순환).
- 의뢰자 자원 부족 시 보상 일부 감액.

### 월드 피드백
퀘스트 완료 이벤트 → WorldEventBus 발행:
- `bulk_delivery` 완료 → 해당 node stockpile 증가 → agent needs 감소
- `raider_suppress` 완료 → raider.strength 감소 → safety needs 회복
- `road_restore` 완료 → edge.severed = False → 상인 이동 재개

---

## M6 — 세력(Faction) + 명성 시스템

### 목표
월드에 소속(세력)이 생기고, 플레이어의 명성이 세력별로 관리된다.

### 설계

#### Faction
```python
@dataclass
class Faction:
    id: str
    name: str
    home_region: str          # 거점 node
    member_ids: list[str]     # 소속 agent id
```

#### 명성 전파 (부분 지식 모델)
- 플레이어와 **직접 상호작용**한 agent만 실제 명성을 앎.
- 같은 node에 있는 agent끼리 일정 확률로 명성 정보를 공유 (소문).
- agent는 자신이 아는 명성만 가격·태도에 반영.

```python
# Agent에 추가
known_player_rep: dict[str, float] = field(default_factory=dict)  # faction_id → rep
```

#### 명성 효과
| 명성 구간 | 효과 |
|---|---|
| +60 이상 | 해당 세력 NPC 가격 10% 할인, 전용 퀘스트 해금 |
| +30 ~ +60 | 우호적 대화, 정보 공개 |
| -30 ~ +30 | 중립 |
| -60 이하 | 거래 거부, 전투 선제 공격 |

#### 명성 변화 이벤트
- 퀘스트 완료 → 의뢰자 세력 명성 +10~30 (urgency 비례)
- 퀘스트 실패/만료 → 의뢰자 세력 명성 -5
- 상인 약탈 → 피해 세력 명성 -20

---

## M7 — 맵 확장 (다중 도시·국가)

### 목표
3-node 선형 맵 → 다중 도시 그래프. agent 수 확장.

### 확장 단계
1. **도시 추가**: 새 node + edge (config yaml로 정의)
2. **국가(State) 개념**: Faction의 상위 레벨. 외교 상태(전쟁·화평)
3. **agent 수 스케일**: 50 → 200+ (성능 검증 병행)

### 성능 목표
- LLM 없는 1 tick: < 50ms (200 agent 기준)
- QuestGenerator (LLM 포함): < 30s / 168 tick 주기

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
