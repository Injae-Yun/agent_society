# Agent-Society — Research Landscape & Positioning

> 본 문서는 Agent-Society 프로토타입의 방향을 잡기 위해 조사한 선행 연구·프로젝트를
> 개괄합니다. 세부 레퍼런스는 각 하위 문서 및 `references.md` 참조.

---

## 1. 프로젝트 한 줄 정의

**결핍·욕구 기반 에이전트 사회 시뮬레이션 + 외부 이벤트 유발 + 로컬 LLM에 의한
Quest 서사화**를 결합한 RPG 프로토타입.

---

## 2. 3-System 아키텍처

| 시스템 | 역할 | 대응 선행 연구 |
|---|---|---|
| **Event Generator** | 외부/환경 이벤트 발행 (도로 단절, 자원 고갈, 재해 등) | RimWorld AI Storyteller, L4D AI Director, Riedl의 Drama/Experience Manager 계열 |
| **Agent Society** | 위치·이동 제약하에서 needs/desires로 구동되는 에이전트 시뮬레이션 | Stanford Smallville (Park 2023), Altera Project Sid (2024), Lee & Cho 2014 |
| **Quest Generator** | 욕구·상황을 취합해 플레이어용 자연어 Quest를 생성 (Local LLM) | Värtinen 2022 (Quest-GPT), van Stegeren 2021, Ashby 2023 (KG+LM) |

### 정보 흐름 원칙

- **Event Generator → world**: Agent Society 상태를 **read-only**로 참조, WorldEvent만 발행
- **Agent Society**: 자체 tick으로 needs/행동 업데이트, 내부 이벤트도 WorldEvent 버스로 방출
- **Quest Generator**: 두 시스템 모두 read-only, 플레이어에게 Quest 텍스트를 출력
- **피드백**: Quest 완료 결과는 Agent Society의 need 해소/state change로 반영

### Player의 위치

4번째 시스템이 아닌 **인터페이스 레이어**. Quest generator의 출력을 받고, 행동은
WorldEvent로 agent_society에 주입.

---

## 3. 본 프로젝트의 차별점 (novelty statement)

선행 연구에서 각 축은 개별적으로 깊이 탐구되었지만, 세 축의 결합은 희소함:

- ① **내부 상태(결핍·욕구) 기반 emergent quest trigger** — Smallville/Sid는 여기까진 유사
- ② **물리적 위치·이동 제약이 상호작용의 근본 제약** — Smallville에 있음, Quest 논문은 대부분 없음
- ③ **이를 로컬 LLM이 플레이어용 서사로 번역** — Quest-GPT 계열 있음. 단 ①·② 시뮬과 결합된 공개 사례는 드묾
- ④ **Event generator가 개별 에이전트 needs-aware** — RimWorld는 colony-level만. 본 프로젝트는 agent-level 상태를 읽어 상황 감응적 이벤트 선택

가장 근접한 단일 개념: **Lee & Cho (2014) "Procedural Quest Generation by NPC in MMORPG"**
— NPC desire 모델 기반 퀘스트 생성. LLM 이전 시대라 자연어 서사화가 빈약하다는 한계.

**본 프로젝트 ≈ Lee & Cho 2014의 desire-driven 로직 × Smallville의 에이전트 구조
× 로컬 LLM 서사화.**

---

## 4. 하드웨어·LLM 선택 전제

- 타겟: RTX 5060 (16GB VRAM), 단일 로컬 추론
- 1차 후보: **Gemma 3 4B** 또는 **Gemma 4 E4B** (GGUF Q4_K_M)
- 품질 부족 시: **Gemma 4 26B-A4B (MoE, Q4_K_M)** — 16GB에 fit, ~40–50 tok/s 기대
- LLM은 **Quest 서사화 단계에만** 사용 (에이전트 의사결정은 rule-based)

상세: `04_local_llm_hardware.md`

---

## 5. 문서 맵

- `00_overview.md` — 이 문서
- `01_agent_society.md` — Smallville, Project Sid 심층
- `02_quest_generation.md` — LLM 기반 Quest 생성 선행 연구
- `03_event_generator.md` — AI Director / Drama Manager 계보
- `04_local_llm_hardware.md` — Gemma 모델별 VRAM/성능
- `references.md` — 전체 bibliography
