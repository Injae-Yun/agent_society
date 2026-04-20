# 01. Agent Society — 선행 연구

본 프로젝트의 System 2 (Agent Society) 설계 참고 문헌.

---

## 1.1 Stanford Smallville (Park et al., UIST 2023) ★ 핵심 레퍼런스

**Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith R. Morris, Percy Liang,
Michael S. Bernstein**
*Generative Agents: Interactive Simulacra of Human Behavior*
arXiv: 2304.03442 | Code: https://github.com/joonspk-research/generative_agents

### 핵심

- 25명의 LLM 구동 에이전트를 The Sims 풍 샌드박스 "Smallville"에 배치
- Smallville은 카페, 바, 공원, 학교, 기숙사, 집, 상점 등 작은 마을 시설과
  그 안의 하위 공간(부엌, 화구 등)까지 기능적으로 정의
- 에이전트는 비디오게임처럼 맵을 이동하며 건물 출입, 경로 탐색, 다른 에이전트
  접근 수행. LLM이 "이 장소로 이동"을 지시하면 엔진이 walking path를 계산
- 3단 아키텍처: **Observation → Planning → Reflection**
  - Observation: 주변 감각 기록
  - Planning: 하루 일정 + 다음 행동
  - Reflection: 누적 기억을 higher-level 통찰로 합성
- Memory stream: 모든 경험을 자연어로 저장하고, relevance/recency/importance
  점수로 retrieval
- 논문의 대표 시연: "Valentine 파티 열고 싶다"는 한 문장을 주입 → 2일간
  초대·친구 맺기·데이트 약속·시간 맞춰 모이기까지 emergent하게 발생

### 본 프로젝트와의 관계

- **참고**: 위치 기반 이동/상호작용 제약, 3단 아키텍처의 Observation/Planning,
  맵-오브젝트 기능 결합
- **차이**: Smallville은 사회 시뮬레이션이 목적이라 플레이어 Quest 개념 없음.
  욕구 모델이 명시적이지 않고 LLM이 암묵적으로 생성
- **차용할 것**: Memory stream의 간소화 버전, 맵/오브젝트 affordance 정의 방식
- **버릴 것**: 모든 에이전트 의사결정에 LLM을 쓰는 구조 — 우리는 rule-based로

---

## 1.2 Altera Project Sid (2024)

**Altera.AL (founder: Robert Yang)**
*Project Sid: Many-agent simulations toward AI civilization*
arXiv: 2411.00114 | Code: https://github.com/altera-al/project-sid

### 핵심

- 10–1000+ 에이전트, Minecraft 환경
- **PIANO (Parallel Information Aggregation via Neural Orchestration)** 아키텍처
  — 모듈형·병렬적·bottleneck 구조로 서로 다른 기능(반응, 대화, 계획)을
  동시에 돌리면서 일관성 유지
- 관찰된 emergent 현상: 직업 분화, 집단 규칙 준수·수정, 밈·종교(Pastafarianism)
  전파, 상인 허브 형성
- 한계(저자들이 기술): 공간 인지·시각 부재로 Minecraft 기본 스킬(탐색·건축
  협업)에 제약

### 본 프로젝트와의 관계

- **참고**: 모듈형·병렬 아키텍처 철학(특히 tick 내 다중 모듈 업데이트)
- **차용할 것**: "다수 모듈 중 일부만 LLM"이라는 선택적 LLM 사용 패턴
- **버릴 것**: 1000+ 규모 — 우리는 20–100 수준 프로토타입으로 충분

### 부수 인사이트

공개 데모에서 에이전트들이 플레이어 요청을 무시하고 자기 일 하는 경향이
관찰됨. → Quest 시스템 설계 시 "에이전트가 플레이어의 의뢰를 받아 수행"이
아니라 "에이전트의 욕구가 플레이어에게 Quest로 전달"되는 방향이 구조적으로
더 맞음.

---

## 1.3 Lee & Cho (2014) — NPC Desire Model Quest Generation ★ 개념적 원형

*Procedural Quest Generation by NPC in MMORPG* (ResearchGate 264174345)

### 핵심

- NPC의 **desire model + dynamic resource management**로 퀘스트 생성 결정
- 파라미터: desire satisfaction, money deposit, friendship
- 퀘스트 완료 상태가 이 파라미터를 변경 → 다음 퀘스트 생성에 영향
- persistent world RPG 가정

### 본 프로젝트와의 관계

**개념적으로 가장 가까운 선행 연구.** 본 프로젝트는 이 논문의 desire-driven
로직에 Smallville의 공간적 에이전트 구조와 로컬 LLM 서사화를 결합한 형태.

LLM 이전 시대라 퀘스트 텍스트는 템플릿 기반. 우리는 여기에 LLM 서사화 계층을
얹는다고 보면 된다.

---

## 1.4 The Sims — Needs 시스템 (상용 게임)

학술 문헌은 아니나 Needs 모델 설계의 사실상 표준:

- 8 needs (hunger, bladder, social, fun, hygiene, energy, comfort, environment)
- 각 need는 시간에 따라 decay
- 에이전트는 utility AI로 행동 선택 (가장 낮은 need를 채우는 행동 우선)
- 위치 기반: 특정 need 충족은 특정 오브젝트(침대, 냉장고)에서만 가능

### 본 프로젝트와의 관계

**이 모델을 원형으로 차용.** 단 RPG 맥락에 맞게 결핍(deficiency) 카테고리 재설계 필요
(예: safety, belonging, autonomy, craft materials, information 등).

---

## 1.5 설계에 반영할 것 — 요약

1. **Needs**: 기본 decay 되는 base needs + 이벤트로 생기는 situational needs
2. **공간**: 맵 그래프(노드=장소, 엣지=경로) + 노드 내 오브젝트 affordance
3. **이동 제약**: 엣지 단절·혼잡·시간 비용이 이벤트와 Quest의 주 재료
4. **의사결정**: Rule-based (utility AI / GOAP). LLM은 Quest 서사화 단계에만
5. **Memory**: Smallville 풀버전은 과함. "최근 N개 사건 + importance flag"로 시작
6. **"Administrative" 이동 에이전트**: 유저 설계 원안 — 일반 에이전트보다
   넓은 이동 범위 + 문제 해결 능력 보유한 상위 NPC. 플레이어가 닿지 않는
   Quest는 이 상위 에이전트가 해결 (시뮬레이션의 자가-안정화 메커니즘)
