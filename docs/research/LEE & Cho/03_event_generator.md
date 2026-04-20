# 03. Event Generator — 선행 연구 (AI Director / Drama Manager 계보)

본 프로젝트의 System 1 (Event Generator) 설계 참고 문헌.

이 계층은 프로젝트 초안에서 상대적으로 덜 다뤄졌지만, **Quest 생성의 재료가
되는 "상황"을 공급**하는 핵심 축이다.

---

## 3.1 Left 4 Dead — AI Director (상용, 2008)

Valve의 L4D에서 처음 대중화된 개념. 플레이어의 stress level(체력·탄약·최근
전투 강도 등)을 모니터링하면서, 좀비 웨이브·아이템 드롭·환경 변화를 동적으로
조정해 **pacing curve**(긴장-휴식-긴장)를 만든다.

### 본 프로젝트 시사점

- "이벤트 발행은 상태 기반 확률 조정"이라는 기본 패러다임
- pacing curve의 중요성 — Quest도 연속으로 쏟아지면 플레이어가 피로함
- **플레이어 상태도 이벤트 선택 입력**에 포함해야 한다는 점 (4번째 입력)

---

## 3.2 RimWorld AI Storyteller (상용, 2018~) ★ 가장 직접적 레퍼런스

Ludeon Studios. **L4D AI Director에서 영향받아** 콜로니 시뮬로 이식한 시스템.

### 구조

3가지 preset storyteller — 각자 다른 이벤트 발동 스케줄 + 편향:

- **Cassandra Classic**: 긴장 상승 곡선. "푸시 → 숨통 → 푸시"
- **Phoebe Chillax**: 긴 휴식 간격, 대신 가끔 강하게
- **Randy Random**: 규칙 없이 무작위

### 입력 변수 (중요)

이벤트 결정 시 고려하는 것:
- colony wealth (부)
- building wealth
- colonists 수
- animal 수
- 최근 colonist 사망·중상 여부
- 마지막 주요 이벤트 이후 경과 시간

### 출력

해적 습격, 상인 도착, 폭풍, 자원 드롭, 야수 습격, 방랑자 합류 등 이벤트 발행.

### 주목할 디자인 결정

- Storyteller는 **ingame body/location이 없는 추상적 선택자**
- **Population cap은 soft** — 높은 인구에서 특정 이벤트(방랑자 합류)의 확률만
  낮아지고 완전히 막히진 않음
- **난이도와 storyteller는 직교** — 같은 Cassandra도 난이도에 따라 강도 달라짐

### 본 프로젝트와의 대조

| 항목 | RimWorld | Agent-Society (본 프로젝트) |
|---|---|---|
| 상태 입력 granularity | colony-level (부·인구) | agent-level (개별 needs) |
| 이벤트의 타깃 | 콜로니 전체 | 특정 에이전트·지역 |
| 이벤트 → 서사 | 수작업 텍스트 템플릿 | LLM이 Quest로 번역 |
| 플레이어 개입 방식 | 직접 조작 (콜로니 관리) | Quest 수락/해결 |

**핵심 차이: 본 프로젝트는 agent-level 상태를 읽어 "이 에이전트/지역에 어떤
이벤트가 가장 이야깃거리를 만들까"를 판단한다.** 예: 광부 에이전트 3명이 있는
마을에 광산 붕괴 이벤트가 선호된다.

---

## 3.3 학계 — Drama Manager / Experience Manager

Georgia Tech의 Mark O. Riedl 그룹이 20년+ 파온 분야. RimWorld 스토리텔러의
formal한 뿌리.

### 주요 계보

- **Weyhrauch (1997)** — Moe: adversarial search 기반 drama management (원조)
- **Young, Riedl et al. (2004) — Mimesis** — plan-based behavior generation을
  Unreal Tournament에 통합. Drama manager가 서버로 작동
- **Nelson, Roberts, Isbell, Mateas (2006)** — Declarative optimization-based
  drama management with reinforcement learning
- **Thue, Bulitko et al. (AIIDE 2007)** — Player modeling 기반 interactive
  storytelling
- **Ontañón et al. (2008)** — Interactive fiction용 drama management architecture
- **Sharma, Santiago, Mehta, Ram (2010)** — Drama management + player modeling,
  case-based reasoning
- **Riedl & Bulitko (2013)** — Survey. "Interactive Narrative: An Intelligent
  Systems Approach"
- **Yu & Riedl (2014)** — Data-driven personalized drama management,
  sequential recommendation of plot points

### 공통 패턴

1. **Experience manager**: 플레이어 경험을 외부에서 모니터링·조정하는 에이전트
2. **Author-defined heuristic**: 바람직한 이야기 궤적에 대한 작가의 사전 정의
3. **Search / RL / planning**: 이벤트·플롯 포인트 선택 최적화
4. **Player modeling**: 플레이어 성향을 학습해 개인화

### 본 프로젝트 시사점

- MVP 단계에선 RimWorld식 **상태 기반 가중 확률표**로 충분
- 확장 단계: player modeling (플레이어가 전투 Quest를 많이 풀면 사회적
  Quest 가중치 상승 등)
- 장기: **LLM 자체를 experience manager로 쓰는 실험** — 월드 상태 요약을
  LLM이 읽고 다음 이벤트를 제안

---

## 3.4 설계 결정 초안

### MVP Event Generator

```
class EventGenerator:
    def tick(self, world_state):
        # 1. 상태 스냅샷: 에이전트 needs, 위치 분포, 최근 Quest 해결률
        snapshot = summarize(world_state)

        # 2. 이벤트 카탈로그 → 조건 필터 → 가중치 계산
        candidates = [e for e in CATALOG if e.preconditions(snapshot)]
        weights = [e.weight_fn(snapshot) for e in candidates]

        # 3. pacing gate — 최근 이벤트 이후 경과 시간
        if not self.pacing_allows(snapshot):
            return None

        # 4. 가중 샘플링
        event = weighted_choice(candidates, weights)
        return event
```

### 이벤트 카탈로그 예시 (초안)

- `RoadCollapse(edge)` — 경로 엣지 하나 단절. 조건: 교통량 있음
- `ResourceDepletion(location, resource)` — 특정 장소 자원 고갈
- `Wanderer(location)` — 새 에이전트 합류. 조건: 인구 적음
- `Feud(agent_a, agent_b)` — 두 에이전트 간 갈등. 조건: 같은 장소 반복 마찰
- `Discovery(location, item)` — 새 자원·장소 발견

### Quest Generator와의 인터페이스

이벤트가 발행되면 곧바로 Quest가 되는 건 아니다:

```
WorldEvent → AgentSociety.ingest(event) → needs 변경 →
  QuestGenerator가 need 임계치 초과 감지 → Quest 생성
```

즉 **이벤트는 needs에 "파동"을 일으키고, needs가 임계치를 넘을 때 Quest가
생성**된다. 이 간접 결합이 설계상 중요하다 (이벤트 ↔ Quest 1:1이 아니라서
더 풍부한 조합이 가능).
