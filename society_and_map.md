# Society & Map — Design (v0.2)

> v0.2 변경: 삼각 → 선형 맵, 군인 제거(개인 무기로 대체), 약탈자 단일 agent화,
> 티어 시스템, 물물교환, 이벤트 카탈로그 중심 재편.

---

## 0. v0.2 변경 요약

| 변경 | From (v0.1) | To (v0.2) |
|---|---|---|
| 맵 배치 | 삼각 (도시·농경지·약탈자 동등) | **선형**: 도시 ↔ 농경지 사이에 약탈자 영역 |
| 루트 | 단일 | **이중 루트** (안전 우회 / 위험 관통) |
| 직업 수 | 11 (군인 포함) | **9** (군인 제거, 과수원·요리사 추가) |
| 군인 | 별도 직업 | 제거. **개인 무기 착용**으로 대체 |
| 약탈자 | 다수 agent | **단일 agent + strength 변수** |
| 티어 | 없음 | **기본 / 상위** 2단계 |
| 통화 | TBD | **물물교환 + 변동 비율** |
| Section 5 | 창발 사이클 서술 | **명시적 이벤트 카탈로그** |
| Quest 생성 | 이벤트 즉시 | **주기적 갱신(~100 tick) + 유사 병합** |

---

## 1. 상위 설계 결정 (TL;DR)

| 항목 | 결정 |
|---|---|
| 직업 | 고정 9종 (농부·목축·광부·과수원 / 대장장이·요리사 / 상인·약탈자). 1차 생산자 4종 |
| 맵 | 그래프 기반, **선형 3지역 + 이중 루트** |
| 공간 점유 | 1차 생산자 전체가 **농경지 단일 지역** 공유 (MVP 단순화) |
| 재화 티어 | 기본 / 상위 2단계 |
| 소비 | 모든 agent가 음식 소비 + **모든 행동이 도구 소비** |
| 통화 | 물물교환, 재화 scarcity에 따라 교환 비율 변동 |
| 약탈자 | 단일 agent. strength가 위협 수준 |
| 군사력 | 개인 무기 착용 여부 → 약탈 상호작용 결과 변경 |
| Quest 생성 | 100 tick 주기, 유사 Quest 병합 |

---

## 2. 맵 구조

### 2.1 선형 3지역 배치

```
        ┌───── 안전 루트 (우회, ~10% 위협, 이동 비용 ↑↑) ─────┐
        │                                                       │
 ┌──────┴─────┐                                           ┌─────┴──────┐
 │  도시 City  │                                           │ 농경지 Farm │
 │ (장인·소비) │                                           │ (1차 생산)  │
 └──────┬─────┘                                           └─────┬──────┘
        │                                                       │
        └─── 위험 루트 (관통, ~70% 위협, 비용 ↓) ────────┐  ┌──┘
                                                         │  │
                                              ┌──────────▼──▼──┐
                                              │  약탈자 본거지  │
                                              │  Raider Base   │
                                              └────────────────┘
```

- 위험 루트는 **약탈자 본거지와 인접** → 약탈자가 매복·습격
- 안전 루트는 우회로 — 길고 느리지만 약탈 위협 낮음
- 상인은 루트를 선택 (납기·경쟁·무기 보유 여부에 따라)

### 2.2 지역 내 노드 (공간 통합 반영)

**도시 (City)**
- `Market` — 거래 중심
- `Smithy` — 대장장이 작업장
- `Kitchen` — 요리사 작업장
- `Residential` — 거주지 (기본 소비 중심)

**농경지 (Farmland) — 1차 생산자 전체 공유**
- `Grain Field` — 농부(밀) 작업지 + 농부 거주
- `Pasture` — 목축업자 작업지 + 거주
- `Orchard` — 과수원 농부 작업지 + 거주 (상위 티어)
- `Mine` — 광부 작업지 + 거주
- `Farmland Hub` — 공용 광장, 내부 거래·상인 접선

> 단순화 결정: 광부·과수원 농부가 농경지 하위 노드에 상주.
> 추후 벌목꾼·사냥꾼 분리 시에도 같은 패턴으로 확장 가능.

**약탈자 본거지 (Raider Base)**
- `Hideout` — 약탈자 agent 상주

### 2.3 엣지 속성

```python
# 스키마
Edge:
    u, v: NodeId
    travel_cost: int     # tick 수
    base_threat: float   # 0.0 ~ 1.0, 약탈 조우 확률
    capacity: int        # 동시 이용 가능 agent 수
    severed: bool = False
```

**MVP 수치 초안**:

| 루트 | travel_cost | base_threat | capacity |
|---|---|---|---|
| 안전 루트 (도시↔농경지 우회) | 30 tick | 0.10 | 2 |
| 위험 루트 (도시↔농경지 관통) | 10 tick | 0.70 | 2 |
| 도시 내부 | 1–3 tick | 0.0 | ∞ |
| 농경지 내부 | 1–3 tick | 0.0 | ∞ |
| 약탈자 본거지 진입 | 20 tick | 0.0 | 1 (공격용) |

**도로 용량**: 초과 시 대기 발생 → 상인이 "빠른 대신 위험" 루트를 선택하는 압력.

### 2.4 동적 지도 변화

이벤트로 엣지 속성이 일시 변경:
- `RoadCollapse` — severed = True (수리 Quest로 해소)
- `WeatherDisruption` — travel_cost 일시 ↑
- `RaiderBlockade` — base_threat 일시 ↑↑
- `MilitiaPatrol` — base_threat 일시 ↓ (Quest 보상 효과)

---

## 3. 직업 체계 (9종)

### 3.1 직업 분류표

| 분류 | 직업 | 위치 | 산출 (티어) | 주 소비 |
|---|---|---|---|---|
| **1차 생산 (기본)** | 농부 (Farmer) | Grain Field | 밀 (기본 식품) | 음식·농기구 |
|  | 목축업자 (Herder) | Pasture | 고기 (기본 식품) | 음식·도구 |
|  | 광부 (Miner) | Mine | 광석 (원자재) | 음식·곡괭이 |
| **1차 생산 (상위)** | 과수원 농부 (Orchardist) | Orchard | 과일 (상위 식품) | 음식·농기구 |
| **2차 생산** | 대장장이 (Blacksmith) | Smithy | 농기구·무기 | 음식·광석·망치 |
|  | 요리사 (Cook) | Kitchen | 요리 (상위 식품) | 기본 재료·조리도구 |
| **특수직** | 상인 (Merchant) | Market (순회) | — (지역 간 재화 운반) | 음식·무기·짐수레 |
|  | 약탈자 (Raider) | Hideout | — (강제 추출) | 음식·무기 |

*(MVP에 없음: 군인, 어부, 사냥꾼, 벌목꾼, 제빵사. 제빵은 요리사로 통합.)*

### 3.2 티어 시스템

**식품**은 두 층:
- **기본 식품** (밀, 고기) — `hunger` 해소. 필수
- **상위 식품** (과일, 요리) — `food_satisfaction` 해소. 선택적이지만 만족도 영향

**필요한 가공**:
- 밀 그대로 섭취 가능 (기본 hunger 해소). 요리사가 가공하면 상위 식품화
- 고기 그대로 섭취 가능. 요리로 업그레이드 가능
- 과일은 과수원 직출이 곧 상위 식품

*(요리사 레시피 세부는 Open Question. MVP: 요리사는 "기본 재료 2종 이상 → 상위 요리 1" 추상 변환)*

### 3.3 도구 소비 (보편)

**모든 행동에는 도구가 필요하고 사용 시 내구도가 소모**된다.

| 직업 | 필요 도구 | 소모 속도 |
|---|---|---|
| 농부 | 쟁기·낫 | 매 생산 시 -1 |
| 목축업자 | 낫·도구 | 매 생산 시 -1 |
| 광부 | 곡괭이 | 매 생산 시 -1 |
| 과수원 농부 | 전지가위·사다리 | 매 생산 시 -1 |
| 대장장이 | 망치·화로 (상위 내구) | 매 생산 시 -1 |
| 요리사 | 조리도구 | 매 생산 시 -1 |
| 상인 | 짐수레 | 매 이동 시 -1 |
| (무기) | 검·활 | 전투 발생 시 -1 |

내구도 소진 시 → 해당 agent의 `tool_replacement` need 급상승 → 대장장이에 주문
→ (지역 간이면) 상인 개입 필요.

→ **이 순환이 경제의 기본 동력**. 약탈자 영향은 이 순환을 방해하는 외력.

### 3.4 무기 착용 시스템 (군인 대체)

모든 agent는 무기 슬롯을 가지며 **착용 선택**:

```python
Agent.equipped_weapon: Optional[Item]  # 검·활 등, 내구도 보유
```

**약탈자 조우 시 판정**:

| 피습자 무기 상태 | 결과 |
|---|---|
| 무기 있음 + 내구도 ≥ 1 | 방어 시도 → 약탈자 strength와 비교 판정. 무기 -1 |
| 무기 없음 또는 내구도 0 | 일방적 피습 (재화 손실, safety need 급상승) |

**방어 판정 (단순)**:
```python
def raid_resolution(defender, raiders):
    if not defender.has_usable_weapon():
        return "robbed", full_loot
    defender_power = weapon_power(defender.equipped_weapon)
    if defender_power >= raiders.strength * 0.8:
        return "defended", no_loot  # 무기 -1, 약탈자 strength -small
    else:
        return "partial_loss", partial_loot  # 무기 -1
```

**귀결**:
- 상인은 사실상 무기 필수 → 대장장이 수요의 주 고객
- 농부·광부도 점차 무장 → 대장장이 수요 확대
- 약탈자 strength가 높아지면 개인 무장 불충분 → "본거지 공격" Quest 필요

---

## 4. 경제·재화

### 4.1 재화 카테고리

- **기본 식품**: 밀, 고기
- **상위 식품**: 과일, 요리
- **원자재**: 광석
- **장인 제품**: 농기구(쟁기·낫·곡괭이·전지가위), 무기(검·활), 조리도구, 짐수레

### 4.2 공급망

```
  광부 ─── 광석 ────┐
                     │
  목축 ─── 고기 ─────┤                  ┌── 농기구 → 1차 생산자
                     │                    │
  농부 ─── 밀 ──┐    ▼                    ├── 무기 → 모두
             │ 대장장이 ───────────────┘
             │                                   (모든 도구는 소모)
             ├───► 요리사 ─── 요리 (상위)
             │
  과수원 ─── 과일 (상위) ──┐
                            ▼
                     [모든 agent: 음식 소비]
```

- 1차 생산자는 자체 식품을 먹거나 (공간 공유), 상인을 통해 다른 1차 생산물 교환
- 도시 거주자 (장인)는 상인이 가져오는 농경지 식품 의존
- 상위 식품은 요리사 경유 시 품질 상승 + 과수원 직출

### 4.3 물물교환 + 변동 비율

MVP는 통화 도입 미룸. **물물교환 + scarcity-based 변동 비율**.

```python
# 각 재화에 기준 가치 (상수)
BASE_VALUE = {
    "wheat": 1.0,
    "meat": 2.0,
    "fruit": 3.0,       # 상위
    "cooked_meal": 4.0, # 상위
    "ore": 2.0,
    "plow": 8.0,
    "sword": 12.0,
    # ...
}

def exchange_rate(item_a, item_b, world_stock):
    # 기준 비율
    base = BASE_VALUE[item_a] / BASE_VALUE[item_b]
    # 수급 보정: a가 흔하면 싸짐, b가 드물면 비싸짐
    scarcity_a = 1.0 / max(world_stock[item_a], 1)
    scarcity_b = 1.0 / max(world_stock[item_b], 1)
    return base * (scarcity_b / scarcity_a)
```

**예**: 흉년으로 밀 재고 급감 → 밀의 scarcity ↑ → 밀 1 = 고기 3 (평시 1:2에서).

**단순화 원칙**: MVP는 **pairwise 교환만**, 복합 거래 없음. scarcity_factor도 단순 공식.

### 4.4 약탈자의 강제 추출

```python
def raid_action(raiders, target_node):
    defense = sum(w.power for w in armed_agents(target_node))
    if defense >= raiders.strength:
        return "repelled", 0
    loot = target_node.stockpile.take(proportion=RAID_RATE)
    raiders.consume(loot)
    raiders.strength += STRENGTH_GAIN_FROM_SUCCESS
    target_node.agents.add_need("safety", HIGH)
    target_node.agents.add_need("retaliation", MEDIUM)
    destroyed = loot.fraction(DESTRUCTION_FACTOR)
    return "plundered", loot - destroyed
```

---

## 5. 이벤트 카탈로그

> v0.2 관점 변경: **창발 사이클을 설계하지 않는다.**
> 대신 **명시적 이벤트를 시뮬레이션에 주입**하고, 그것이 needs → Quest로
> 번지는 경로만 잘 연결해 둔다. 창발 현상은 관찰 목표지 설계 목표가 아니다.

### 5.1 자연·경제 이벤트

| 이벤트 | 효과 | 빈도 (초안) |
|---|---|---|
| 풍년 (Harvest Boom) | 1차 생산 +50%, 1 season | 3–5년 주기 |
| 흉년 (Harvest Failure) | 1차 생산 -50%, 1 season | 3–5년 주기 |
| 광맥 발견 | 광부 생산 2배, ~10일 | 희소 |
| 광맥 고갈 | 광부 생산 -50%, 영구 (복구 Quest로만 해소) | 희소 |
| 대량 주문 (Bulk Order) | 특정 장인 제품 수요 급증 | 랜덤 |

### 5.2 약탈자 관련 이벤트

| 이벤트 | 효과 | 트리거 |
|---|---|---|
| 약탈자 강화 (Raider Surge) | strength +30% | 식량 부족 지속·습격 성공 누적 |
| 약탈자 약화 (Raider Decline) | strength -30% | 기근·본거지 공격 성공 |
| 약탈자 봉쇄 (Road Blockade) | 위험 루트 차단 또는 base_threat ↑↑ | strength 임계 초과 시 |
| 약탈자 내분 | strength -50%, 일시 | 랜덤 희소 |

### 5.3 경로·재해 이벤트

| 이벤트 | 효과 |
|---|---|
| 도로 붕괴 (Road Collapse) | 특정 엣지 severed |
| 악천후 | travel_cost ×2, 3–7일 |
| 도로 복구 | severed 해제 (Quest 해결) |

### 5.4 이벤트 → needs → Quest 경로

```
Event Generator
     │
     ▼
WorldEvent 발행 (예: 흉년)
     │
     ▼
Agent Society가 구독
     │
     ▼
해당 agent의 needs 수치 조정
  (예: 농부·전체의 음식 needs ↑)
     │
     ▼ (다음 QuestGenerator tick, ~100 tick 후)
Quest Generator가 임계치 초과 needs 수집
     │
     ▼
QuestIntent 생성 → 유사 병합 → LLM 서사화
     │
     ▼
플레이어에게 Quest 제시
```

---

## 6. 약탈자 시스템 상세

### 6.1 단일 agent + strength 모델

**추상화**: 약탈자 "집단"을 하나의 agent로 표현.

```python
class RaiderFaction(Agent):
    role = Role.RAIDER
    strength: float       # 0.0 ~ 100.0
    hunger: float
    stockpile: Dict[str, int]
    home = "raider_base.hideout"
```

### 6.2 strength 변동 요인

| 요인 | Δstrength |
|---|---|
| 습격 성공 (대량) | +5 |
| 습격 실패 (격퇴) | −3 |
| 본거지 공격 당함 | −20 (Quest 1회) |
| 이벤트 "약탈자 강화" | +30 |
| 이벤트 "약탈자 약화" | −30 |
| 굶주림 지속 | −1 / day |

### 6.3 습격 판정

- 약탈자 `hunger`가 임계치 초과 → 위험 루트 매복 또는 농경지 노드 습격
- 대상이 상인이면 무기 판정, 농경지 노드면 노드 내 무장 agent 합산
- 결과: repelled / partial / plundered

**본거지 공격 가능성**: 플레이어·자유 이동 NPC가 `raider_base.hideout`에 진입해
공격 → 성공 시 strength 크게 감소. 실패 시 공격자 자신이 피해.

---

## 7. Needs 구조

### 7.1 4종 욕구 (v0.2 합의)

모든 agent가 이 네 가지를 갖는다:

1. **기본 음식 욕구** (`hunger`) — 시간 decay. 기본 식품으로 해소
2. **상위 음식 욕구** (`food_satisfaction`) — 느린 decay. 상위 식품으로 해소
3. **도구/자원 욕구** (`tool_need`) — 사용 시마다 내구도 감소로 상승
4. **safety 욕구** (`safety`) — 위협 근접·습격 체험 시 급상승

### 7.2 직업별 specialized

직업마다 어떤 도구·자원이 주 대상인지만 다를 뿐, 4종 구조는 공통:

| 직업 | 주 tool_need 대상 |
|---|---|
| 농부 | 쟁기·낫 |
| 광부 | 곡괭이 |
| 대장장이 | 원자재 (광석) + 망치 |
| 요리사 | 기본 재료 + 조리도구 |
| 상인 | 짐수레 + 무기 |
| (공통) | 무기 (선택) |

### 7.3 Situational Needs

이벤트가 부여하는 일시 needs:
- `route_restored` — 도로 복구 요구
- `raider_suppression` — 약탈자 제거 요구
- `bulk_delivery` — 대량 주문 이행 요구

이들은 이벤트 소멸 시 자동 감소.

---

## 8. Quest 생성 규칙

### 8.1 주기적 갱신

```python
class QuestGenerator:
    REFRESH_INTERVAL = 100  # tick

    def tick(self, world):
        if world.tick % self.REFRESH_INTERVAL != 0:
            return
        self.refresh(world)

    def refresh(self, world):
        # 1. 임계 초과 needs 수집
        candidates = self.collect_urgent_needs(world)
        # 2. QuestIntent 변환
        new_intents = [self.to_intent(n) for n in candidates]
        # 3. 기존 Quest와 유사도 매칭 → 병합
        for intent in new_intents:
            if (existing := self.find_similar(intent)):
                existing.merge(intent)
            else:
                self.active.append(intent)
        # 4. 변경·신규 Quest만 LLM 서사화
        for q in self.active:
            if q.is_dirty():
                q.narrative = self.narrate(q)
```

### 8.2 유사 Quest 병합

유사도 기준 (structural match):
- 같은 `quest_type` (예: 도로 복구 / 약탈자 제거)
- 같은 `target` (같은 엣지·노드·재화)
- 또는 겹치는 `supporters` 집합

병합 시:
- `supporters` 합산
- `reward` 합산 (공동 의뢰 가산 포함)
- `urgency` = max
- LLM 재서사화 트리거

### 8.3 보상 에스컬레이션

```python
def reward(quest):
    base = quest.type.base_reward
    urgency_mult = 1.0 + quest.urgency            # 1.0 ~ 3.0
    coalition = 1.0 + 0.2 * len(quest.supporters)
    delay = 1.0 + 0.05 * quest.ticks_pending
    return base * urgency_mult * coalition * delay
```

---

## 9. MVP 파라미터 초안

| 항목 | 값 |
|---|---|
| 전체 agent 수 | **~25** |
| 도시 agent | 6–8 (장인 2 + 거주자 3–5 + 상인 2) |
| 농경지 agent | 12–15 (4개 생산 유형 × 3~4명) |
| 약탈자 agent | **1** (단일) |
| 노드 총합 | ~12 (도시 4, 농경지 5, 약탈자 1, 경로 분기 2) |
| Tick 단위 | 10초 in-game |
| 1일 tick 수 | 144 |
| Quest 갱신 주기 | 100 tick (≈ 17분 in-game) |
| Season 길이 | 30 days ≈ 4320 tick |

---

## 10. 3-System 통합 포인트

| System | Reads | Writes |
|---|---|---|
| Event Generator | 월드 스냅샷 (needs 분포, 이벤트 이력, 계절) | `WorldEvent` |
| Agent Society | `WorldEvent`, tick | needs·stockpile·agent 위치·도구 내구 |
| Quest Generator | needs, 이벤트, 활성 Quest 목록 | `QuestIntent` → 자연어 Quest |
| Player / Free NPC | Quest 목록 | `WorldEvent` (해결 결과) |

---

## 11. 데이터 스키마 초안 (dev env 전환용)

```python
# agent_society/schema.py (초안)

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

class Role(Enum):
    FARMER = "farmer"
    HERDER = "herder"
    MINER = "miner"
    ORCHARDIST = "orchardist"
    BLACKSMITH = "blacksmith"
    COOK = "cook"
    MERCHANT = "merchant"
    RAIDER = "raider"

class RegionType(Enum):
    CITY = "city"
    FARMLAND = "farmland"
    RAIDER_BASE = "raider_base"

class Tier(Enum):
    BASIC = "basic"
    PREMIUM = "premium"

@dataclass
class Node:
    id: str
    name: str
    region: RegionType
    stockpile: Dict[str, int] = field(default_factory=dict)
    affordances: List[str] = field(default_factory=list)

@dataclass
class Edge:
    u: str
    v: str
    travel_cost: int
    base_threat: float = 0.0
    capacity: int = 1
    severed: bool = False

@dataclass
class Item:
    type: str
    tier: Tier
    durability: int
    max_durability: int

@dataclass
class Agent:
    id: str
    name: str
    role: Role
    home_node: str
    current_node: str
    needs: Dict[str, float] = field(default_factory=dict)
    inventory: Dict[str, int] = field(default_factory=dict)
    tools: List[Item] = field(default_factory=list)
    equipped_weapon: Optional[Item] = None

@dataclass
class RaiderFaction(Agent):
    strength: float = 30.0  # 0 ~ 100

@dataclass
class World:
    nodes: Dict[str, Node]
    edges: List[Edge]
    agents: Dict[str, Agent]
    tick: int = 0
    active_events: List["WorldEvent"] = field(default_factory=list)
```

---

## 12. 해결된 / 남은 Open Questions

### 해결됨 (v0.2)

| # | 이슈 | 결정 |
|---|---|---|
| 1 | 일반 소비자 | 미도입 |
| 2 | 상위 NPC | 당장 미도입, 추후 판단 |
| 3 | 통화 | 물물교환 + scarcity 기반 변동 비율 |
| 4 | 약탈자 표현 | 단일 agent + strength 변수 |
| 5 | 본거지 공격 | 가능, strength 감소 효과 |
| 6 | 상인 루트 | 경쟁 + 도로 용량 + 이중 루트 선택 |
| 7 | 군인 | **제거.** 개인 무기 착용으로 대체 |
| 8 | Quest 갱신 | 100 tick 주기, 유사 병합 |

### 남은 Open Questions

1. **요리사 레시피 범위**
   - "기본 재료 N종 조합 → 상위 요리"의 N과 조합 규칙?
   - MVP 제안: N=2, 임의 기본 재료 2종 → 상위 요리 1 (추상적)
2. **밀 섭취 가능성**
   - 밀 그대로 먹을 수 있나, 요리사 가공 필요한가?
   - MVP 제안: **그대로 섭취 가능**하나 만족도 낮음 (요리 시 상위 식품화)
3. **재화 base_value 수치**
   - 밀 1.0을 기준으로 한 상대값 테이블 구체화 필요
4. **도로 용량 초과 시 처리**
   - 대기 큐? 위험 루트 강제 선택?
5. **과수원 계절성**
   - 과일은 1년 내내 나오나, 수확기만 있나?
   - MVP 제안: 계절성 있음 (풍년·흉년 이벤트와 맞물림)
6. **약탈자 소멸 조건**
   - strength 0 = 완전 소멸인가, 휴면인가?
   - MVP 제안: strength 0 = 휴면. 시간 경과로 자연 회복 (긴장 유지)
7. **무기 파워 수치**
   - 검 vs 활 vs 비무장의 구체 파워 밸런싱

---

## 다음 단계

이 v0.2 합의 후:
1. `ARCHITECTURE.md` — 3-system 코드 경계, `WorldEvent` 버스, tick loop
2. `folder_structure.md` — Python 패키지 레이아웃
3. 개발 환경 전환 → MVP M1 구현 (월드·노드·agent·tick 스켈레톤)
