# Architecture (v0.2)

> 본 문서는 Agent-Society의 **코드 수준 아키텍처**를 정의한다.
>
> | 관련 문서 | 내용 |
> |---|---|
> | `docs/design/society_and_map.md` | 직업·맵·경제·Quest 사이클 상위 설계 |
> | `docs/design/folder_structure.md` | Python 패키지 레이아웃 |
> | `docs/research/04_local_llm_hardware.md` | LLM 모델 선택·VRAM 예산·Ollama 설정 |
> | `PLAN.md` | 마일스톤별 구현 범위 및 일정 |
> | `configs/default.yaml` | LLM 백엔드·시뮬 파라미터 런타임 설정 |

---

## 0. 설계 원칙

1. **관심사 분리**: 3개 핵심 시스템 + 1개 I/O 레이어. 각 시스템은 자기 담당 상태만 쓴다.
2. **단일 이벤트 버스**: 모든 상태 변경 사유(trigger)는 `WorldEvent`로 표현되고,
   구독자들이 각자 반응한다.
3. **Read-only snapshot**: 시스템 tick 시 월드 상태는 읽기 전용 스냅샷으로 넘긴다.
   쓰기는 반드시 자기 시스템 내부에서만.
4. **LLM은 말단에만**: LLM 호출은 Quest 서사화 한 군데로 한정. 시뮬 루프는
   LLM 없이도 돌아간다 (LLM 백엔드 교체·mock 가능).
5. **결정적 재현성**: 같은 seed + 같은 입력 → 같은 결과. LLM 단계는 예외로
   취급하되 로그·재연 가능하게 기록.

---

## 1. 시스템 구성

```
┌─────────────────────────────────────────────────────────────────┐
│                          SimulationDriver                        │
│                           (tick loop)                            │
└───┬──────────────┬──────────────┬──────────────┬──────────────┬─┘
    │              │              │              │              │
    ▼              ▼              ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Event  │  │  Agent   │  │  Quest   │  │  Player  │  │  World   │
│  Gen   │  │ Society  │  │   Gen    │  │   I/O    │  │  State   │
└────┬───┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │           │             │             │             │
     └───────────┴─────────────┴─────────────┴─────────────┘
                              │
                              ▼
                   ┌─────────────────────┐
                   │   WorldEvent Bus    │
                   │    (pub/sub)        │
                   └─────────────────────┘
```

**구성 요소**:

| 컴포넌트 | 책임 | 쓰기 권한 |
|---|---|---|
| `World` | 모든 상태(노드·엣지·agent·tick)의 저장소 | (system이 간접 수정) |
| `EventGenerator` | 외부 이벤트 발행 조건 평가, 이벤트 게시 | 이벤트 버스만 |
| `AgentSociety` | agent behavior tick, needs decay, 생산·소비·거래·약탈 | agent 상태, 노드 재고 |
| `QuestGenerator` | needs 수집, QuestIntent 생성·병합, LLM 서사화 | 활성 Quest 목록 |
| `PlayerInterface` | Quest 목록 제시, 플레이어 행동 수신 | 플레이어 상태, 이벤트 버스 |
| `WorldEventBus` | pub/sub 브로커. 이벤트 순서 보장 | — |
| `SimulationDriver` | tick 순서 관리, 전체 시뮬레이션 loop | tick 카운터 |

---

## 2. World 상태 모델

### 2.1 World 객체

```python
# schema.py 참조 (society_and_map.md §11)
@dataclass
class World:
    nodes: Dict[NodeId, Node]
    edges: List[Edge]
    agents: Dict[AgentId, Agent]
    tick: int
    active_events: List[WorldEvent]
    # 파생 인덱스 (빠른 조회용, 시스템이 갱신)
    agents_by_node: Dict[NodeId, List[AgentId]]
    agents_by_role: Dict[Role, List[AgentId]]
```

### 2.2 Snapshot

시스템 tick 시 월드는 `WorldSnapshot`으로 넘긴다:

```python
class WorldSnapshot:
    """Read-only view. 시스템은 이걸 받고 의사결정만 한다."""
    def get_node(self, id: NodeId) -> Node: ...
    def get_agent(self, id: AgentId) -> Agent: ...
    def agents_at(self, node: NodeId) -> List[Agent]: ...
    def edges_from(self, node: NodeId) -> List[Edge]: ...
    def scarcity(self, good: str) -> float: ...
    # ...
```

Snapshot은 실제 World 객체를 proxy하는 형태 (deep copy 비용 회피). 단 쓰기
메서드를 노출하지 않는다.

### 2.3 Mutation 규칙

**누가 무엇을 쓰는가** (strict):

| 필드 | 쓰기 권한 |
|---|---|
| `node.stockpile` | AgentSociety (생산·소비·거래), 이벤트 처리기 |
| `edge.severed`, `edge.base_threat` | 이벤트 처리기 (EventGen → WorldEvent 반영) |
| `agent.current_node` | AgentSociety |
| `agent.needs` | AgentSociety, 이벤트 처리기 |
| `agent.inventory`, `agent.tools` | AgentSociety |
| `raider.strength` | AgentSociety (습격 판정), 이벤트 처리기 |
| `world.active_events` | WorldEventBus |
| `world.tick` | SimulationDriver |

위반 시 단위 테스트로 잡는다 (World 객체에 mutation logger 심어서 검증).

---

## 3. WorldEvent 버스

### 3.1 이벤트 계층

```python
from enum import Enum

class EventSeverity(Enum):
    INFO = 0     # 로그용
    MINOR = 1    # 단일 agent 영향
    MAJOR = 2    # 지역 영향
    CRITICAL = 3 # 다수 지역 영향

@dataclass
class WorldEvent:
    id: str           # UUID
    tick: int         # 발생 tick
    source: str       # "event_gen" | "agent_society" | "player" | ...
    severity: EventSeverity
    # — 하위 클래스에서 상세 필드

# 자연·경제
@dataclass
class HarvestBoom(WorldEvent): region: RegionType; duration: int
@dataclass
class HarvestFailure(WorldEvent): region: RegionType; duration: int
@dataclass
class PlagueOutbreak(WorldEvent): node: NodeId; duration: int
@dataclass
class BulkOrder(WorldEvent): good: str; quantity: int; requester: AgentId

# 약탈자
@dataclass
class RaiderSurge(WorldEvent): delta_strength: float
@dataclass
class RaiderDecline(WorldEvent): delta_strength: float
@dataclass
class RaidAttempt(WorldEvent):
    target_node: NodeId
    result: Literal["repelled", "partial", "plundered"]
    loot: Dict[str, int]

# 경로
@dataclass
class RoadCollapse(WorldEvent): edge: tuple[NodeId, NodeId]
@dataclass
class RoadRestored(WorldEvent): edge: tuple[NodeId, NodeId]

# 플레이어·NPC 행동
@dataclass
class QuestAccepted(WorldEvent): quest_id: str; acceptor: AgentId
@dataclass
class QuestResolved(WorldEvent): quest_id: str; success: bool
```

### 3.2 Pub/Sub 인터페이스

```python
class WorldEventBus:
    def publish(self, event: WorldEvent) -> None: ...
    def subscribe(
        self,
        event_type: Type[WorldEvent],
        handler: Callable[[WorldEvent, World], None],
        priority: int = 0,
    ) -> SubscriptionId: ...
    def unsubscribe(self, sub_id: SubscriptionId) -> None: ...
    def drain(self, world: World) -> List[WorldEvent]:
        """해당 tick에 쌓인 이벤트를 subscriber에게 전달하고 비운다."""
```

**순서 보장**:
- 발행 순서 FIFO
- 같은 타입 subscriber 간 priority 오름차순 실행
- 이벤트 처리 중 새 이벤트 발행 가능 (cascade) — 다음 tick이 아닌 **같은
  drain()** 에서 처리 (단, cascade depth 제한 3단계로 무한루프 방지)

### 3.3 이벤트 처리기 예시

```python
# agents/needs.py
def handle_harvest_failure(event: HarvestFailure, world: World):
    for agent in world.agents_by_role[Role.FARMER]:
        if agent.current_region == event.region:
            agent.productivity_mul *= 0.5
            # duration은 별도 카운트다운 처리

# events/bus.py 또는 startup
bus.subscribe(HarvestFailure, handle_harvest_failure)
```

---

## 4. Tick Loop

### 4.1 기본 순서

```python
class SimulationDriver:
    def world_tick(self) -> None:
        w = self.world
        
        # 1. 외부 이벤트 발행 (Event Generator)
        self.event_gen.tick(WorldSnapshot(w))
        
        # 2. 이벤트 적용 (subscriber가 세계 상태 갱신)
        events = self.bus.drain(w)
        w.active_events.extend(events)
        
        # 3. Agent Society tick (agent 행동·needs decay)
        self.agent_society.tick(w)
        
        # 4. Agent 행동에서 발행된 이벤트도 drain
        events = self.bus.drain(w)
        w.active_events.extend(events)
        
        # 5. Quest Generator (주기적)
        if w.tick % QUEST_REFRESH_INTERVAL == 0:
            self.quest_gen.tick(WorldSnapshot(w))
        
        # 6. 플레이어·자유 NPC I/O
        self.player_interface.tick(w)
        events = self.bus.drain(w)
        w.active_events.extend(events)
        
        # 7. 소멸 이벤트 정리 (duration 만료)
        w.active_events = [e for e in w.active_events if not e.is_expired(w.tick)]
        
        # 8. tick 증가
        w.tick += 1
```

### 4.2 Tick 주기 차이

| 시스템 | 주기 | 이유 |
|---|---|---|
| Event Generator | **매 tick** (단 발행은 조건부) | 실시간 감시 필요 |
| Agent Society | **매 tick** | 행동·needs decay 매 tick |
| Quest Generator | **100 tick** | LLM 호출 비용 + 플레이어 피로도 |
| Player I/O | **매 tick** | 입력 즉시 반영 |

Quest Generator의 100 tick 주기는 상수로 관리 (`config.QUEST_REFRESH_INTERVAL`).

### 4.3 Agent 내부 tick

AgentSociety는 각 agent마다 다음을 수행:

```python
def tick_agent(self, agent: Agent, world: World):
    # 1. needs decay
    agent.needs.decay()
    
    # 2. 행동 선택 (utility AI)
    action = select_action(agent, WorldSnapshot(world))
    
    # 3. 행동 실행
    action.execute(world, self.bus)   # 실행 중 이벤트 발행 가능
    
    # 4. 도구 소모
    if action.uses_tool:
        agent.consume_tool(action.tool_type)
```

`select_action`은 utility AI (각 후보 행동의 need 해소 점수 비교). LLM 미사용.

**행동 후보 예시**:
- `ProduceAction` (생산자)
- `CraftAction` (장인)
- `ConsumeFoodAction` (모든 agent)
- `TradeAction` (지역 내)
- `TravelAction` (이동, 상인/약탈자/자유 NPC)
- `RaidAction` (약탈자 전용)

### 4.4 결정적 실행

- Agent tick 순서: agent ID 오름차순
- 동일 엣지 capacity 충돌: agent ID 낮은 쪽 우선
- 난수: 각 시스템이 자체 RNG 보유 (seeded), 전역 `random` 미사용

---

## 5. 시스템 인터페이스 (공개 API)

### 5.1 EventGenerator

```python
class EventGenerator:
    def __init__(self, bus: WorldEventBus, catalog: EventCatalog, rng: Random):
        ...
    
    def tick(self, snapshot: WorldSnapshot) -> None:
        """후보 이벤트 평가 → 조건 충족 시 bus.publish()."""
```

내부:
- `EventCatalog`: 이벤트 템플릿(조건 함수 + 가중치 + 쿨다운) 등록소
- Pacing: 직전 Major/Critical 이벤트 이후 경과 tick 확인

### 5.2 AgentSociety

```python
class AgentSociety:
    def __init__(self, bus: WorldEventBus, rng: Random):
        ...
    
    def tick(self, world: World) -> None:
        """모든 agent의 한 tick 실행."""
    
    def register_handlers(self):
        """이벤트 → needs·상태 변화 핸들러 등록."""
```

### 5.3 QuestGenerator

```python
class QuestGenerator:
    def __init__(self, bus: WorldEventBus, narrator: QuestNarrator):
        ...
    
    def tick(self, snapshot: WorldSnapshot) -> None:
        """수요 수집 → Intent 생성 → 병합 → 서사화."""
    
    def active_quests(self) -> List[Quest]:
        """플레이어·NPC에 노출되는 현재 Quest 목록."""
```

### 5.4 QuestNarrator (LLM 경계)

```python
class QuestNarrator(Protocol):
    def narrate(self, intent: QuestIntent, context: QuestContext) -> str:
        """QuestIntent + 맥락 → 자연어 Quest 본문."""

class OllamaNarrator(QuestNarrator): ...
class MockNarrator(QuestNarrator):
    """테스트용. intent.summary()를 그대로 반환."""
```

LLM 실패 시 fallback: `MockNarrator`로 자동 전환, 로그 남김.

### 5.5 PlayerInterface

```python
class PlayerInterface:
    def tick(self, world: World) -> None:
        """입력 큐 처리 → bus에 이벤트 발행."""
    
    def present_quests(self, quests: List[Quest]) -> None:
        """현재 Quest 목록 UI 출력."""
    
    def submit_action(self, action: PlayerAction) -> None:
        """외부(UI·CLI)에서 호출."""
```

MVP는 CLI 기반. 추후 web UI로 교체 가능하도록 추상화 유지.

---

## 6. LLM 경계

> 상세 모델 선택·VRAM 예산·다운로드 명령은 `docs/research/04_local_llm_hardware.md` 참조.
> 런타임 설정(host·model·temperature 등)은 `configs/default.yaml`.

### 6.1 호출 지점

LLM은 단 한 곳에서만 호출: `QuestNarrator.narrate(intent, context)`.

**입력 — `QuestIntent`**:
- `quest_type`, `target`, `urgency`, `supporters`, `reward`

**입력 — `QuestContext`** (월드 단면 스냅샷):
- 현재 tick·계절
- 긴급 needs 목록: `[(agent_id, role, need_type, urgency_value), ...]` — 임계 초과 agent 전체
- 활성 WorldEvent 요약
- 노드별 scarcity 맵 (주요 재화)
- 의뢰 supporter agent의 페르소나 (이름·직업)

> LLM이 "왜 이 퀘스트가 생겼는가"를 맥락으로 알아야 설득력 있는 서사를 생성함.
> `llm/prompts.py`에서 이 정보를 few-shot 예제와 함께 프롬프트로 조립.

**출력**: 2–4문장 한국어 Quest 서술 문자열.

**⚠ Gemma 4 주의사항**:
- `enable_thinking: false` 필수 — 시스템 프롬프트에 `<|think|>` 토큰 미삽입
- CUDA 12.x 계열 필수 (13.2 사용 시 GGUF 출력 품질 저하)
- Ollama `/api/chat` 사용 (chat template 자동 처리)
- 권장 모델: `gemma4:e4b` (Q8_K_XL, 8.66 GB) — RTX 5060 16GB 기준 KV cache 여유 5.8 GB

### 6.2 비동기 옵션

MVP: **동기 호출** (Quest Gen tick이 LLM 응답 대기).
- 100 tick 주기 × 평균 3초 LLM → 시뮬 속도에 허용 가능
- 실시간 UI가 목적이면 async로 전환:

```python
class AsyncQuestNarrator:
    async def narrate(...) -> str: ...
# Quest는 "narration_pending" 상태로 생성, 완료 시 push
```

### 6.3 Fallback

```python
def safe_narrate(narrator, intent, context, timeout=10):
    try:
        return narrator.narrate(intent, context, timeout=timeout)
    except (LLMTimeout, LLMError) as e:
        log.warning("LLM failed: %s. Using mock.", e)
        return MockNarrator().narrate(intent, context)
```

---

## 7. 데이터 흐름 전체 예시

**시나리오**: 위험 루트에서 상인 Alice가 약탈자에게 습격당함.

```
tick T:
  1. EventGen.tick() — 이벤트 없음
  2. Bus.drain() — 없음
  3. AgentSociety.tick():
       - 약탈자 agent: hunger 임계 → RaidAction 선택
       - Alice: Travel (위험 루트 위)
       - RaidAction 실행: Alice와 조우
         → raid_resolution() 판정
         → Alice 무장 but strength 부족 → "partial_loss"
         → Alice.inventory 50% 감소
         → Alice.needs["safety"] += HIGH
         → 약탈자.hunger 해소, strength +5
         → Bus.publish(RaidAttempt(target=alice_node, result="partial", ...))
  4. Bus.drain():
       - RaidAttempt 핸들러:
         → Alice의 동료 상인들 safety need ↑
         → 도시 거주자들 retaliation need ↑ (뉴스 전파)
  5. Quest tick? — tick % 100 == 0 인 경우만
       - 만약 tick이라면: retaliation/safety 임계 초과 감지
         → QuestIntent "약탈자 제거" 생성
         → 기존 유사 Quest 있으면 병합 (supporters에 Alice 추가)
         → 변경 시 LLM 서사화
  6. PlayerInterface:
       - 새 Quest 있으면 출력
  7. expire events, tick += 1
```

---

## 8. 오류 처리·실패 모드

| 실패 | 완화책 |
|---|---|
| LLM 타임아웃·실패 | MockNarrator fallback, 로그 |
| 이벤트 핸들러 예외 | 해당 이벤트만 스킵, 로그. 시뮬 계속 |
| Capacity 충돌 | 결정적 우선순위 (agent ID) |
| 음수 재고·내구도 | assert. 버그로 간주 |
| 무한 cascade 이벤트 | depth 제한 3, 초과 시 로그·중단 |
| Agent 행동 실패 (자원 없음 등) | 행동 선택에서 pre-check. 무동작 tick은 정상 |

---

## 9. 테스트 전략

### 9.1 단위 테스트

- `world/` — 노드·엣지 CRUD, snapshot 불변성
- `events/` — 각 이벤트 타입의 handler 효과
- `agents/` — 각 role의 행동 선택·needs decay
- `quests/` — 유사도·병합 로직
- `economy/` — 교환 비율 공식

### 9.2 통합 테스트

- 전체 tick loop 10·100·1000 tick 실행
- 특정 시나리오 (흉년 → 기근 → Quest 생성) end-to-end
- LLM은 `MockNarrator`로 결정적 테스트

### 9.3 속성 기반 테스트

- 재화 보존 (total stockpile + agent inventory == constant, 단 소모·생산 제외)
- Quest 병합 아이덤포턴스 (같은 intent 두 번 merge == 한 번)
- 이벤트 순서 FIFO 보장

### 9.4 시나리오 레퍼런스

`tests/scenarios/` 에 YAML로 시나리오 정의 → 재현 가능한 회귀 테스트.

---

## 10. 성능 목표 (MVP)

| 지표 | 목표 |
|---|---|
| Tick 1회 실행 시간 (LLM 없는 tick) | < 50ms |
| Tick 1회 실행 시간 (Quest 갱신 포함, LLM 4B) | < 5s |
| 1일 시뮬 (144 tick, LLM 1–2회) | < 10s |
| 메모리 (~25 agent) | < 200MB |

병목 예상: LLM 호출. Quest Gen 비동기화·캐싱으로 대응 가능.

---

## 11. 확장 지점

향후 확장 시 건드릴 포인트 (잊지 않게 표시):

- **자유 이동 상위 NPC**: PlayerInterface와 같은 인터페이스로 추가 가능
- **멀티 플레이어**: PlayerInterface 다중 인스턴스
- **추가 직업**: `agents/roles.py` 에 role 추가, 이벤트 카탈로그 보강
- **맵 확장**: `world/builder.py` 에 새 지역 추가, 기존 인터페이스 재사용
- **LLM 에이전트 모듈**: 원하면 일부 agent가 LLM으로 의사결정 (opt-in)
- **Web UI**: PlayerInterface를 WebSocket 서버로 교체

---

## 12. 외부 의존성 최소 목록

- Python 3.11+
- `pydantic` 또는 `dataclasses` (스키마) — MVP는 dataclass로 시작
- `pyyaml` — 시나리오 로드
- 로컬 LLM 호출: `ollama` CLI 또는 `ollama-python`, fallback `httpx`
- 테스트: `pytest`, `hypothesis` (속성 기반)
- 린트: `ruff`

GUI·웹 의존성은 MVP 외. CLI는 표준 라이브러리로.
