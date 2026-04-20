# Agent-Society

결핍·욕구 기반 에이전트 사회 시뮬레이션 + 외부 이벤트 유발 + 로컬 LLM Quest 서사화를 결합한 **RPG 프로토타입**.

---

## 빠른 시작

### 1. 설치

```bash
pip install -e ".[dev]"
```

LLM(HuggingFace) 사용 시:
```bash
pip install transformers torch accelerate torchvision
huggingface-cli login
```

### 2. 리플레이 생성 (가장 빠른 확인 방법)

```bash
python scripts/generate_replay.py
```

`output/replay.html` 생성 → 브라우저에서 열면 Time Machine 뷰어 실행.

옵션:
```bash
python scripts/generate_replay.py --ticks 2500   # 기본값 (약 104일, 퀘스트 14사이클)
python scripts/generate_replay.py --ticks 10000  # 긴 시뮬레이션
python scripts/generate_replay.py --output output/my_run.html
python scripts/generate_replay.py --seed 1234
```

### 3. 헤드리스 실행 (터미널 요약만 출력)

```bash
python -m agent_society                         # 기본 2500 tick
python -m agent_society --ticks 10000
python -m agent_society --scenario configs/mvp_scenario.yaml --ticks 5000
python -m agent_society --log-level DEBUG       # 상세 로그
```

---

## 리플레이 뷰어 사용법

| UI | 기능 |
|---|---|
| ◀◀ / ▶▶ | 처음 / 마지막 tick 이동 |
| ◀ / ▶ | tick 단위 이동 |
| ▶ (재생) | 자동 재생 / 일시정지 |
| 슬라이더 | 임의 tick으로 이동 |
| 속도 선택 | 0.5x ~ 10x 재생 속도 |
| 노드 클릭 | 해당 노드의 재고·체류 에이전트 상세 |
| 에이전트 점 클릭 | needs 바, 인벤토리, 행동 상세 |
| **행동 탭** | 해당 tick의 모든 에이전트 행동 목록 |
| **퀘스트 탭** | 현재 활성 퀘스트 목록 (긴급도·서사·보상) |

---

## 시스템 구조

```
WorldSnapshot
    ↓
EventGenerator.tick()    — 자연재해·약탈 이벤트 확률 발생
AgentSociety.tick()      — needs 감소 → 행동 선택 → 실행
QuestGenerator.tick()    — 7일(168 tick)마다: needs 분석 → LLM 서사화
PlayerInterface.tick()   — (M4에서 구현 예정)
```

**퀘스트 흐름:**
```
agent.needs 임계(0.7) 초과
    → bulk_delivery  (hunger/tool_need)
    → raider_suppress (safety)
    → road_restore   (RoadCollapse 이벤트)
    → LLM.narrate()  → quest_text
    → 리플레이 퀘스트 탭에 표시
```

---

## 테스트

```bash
pytest                    # 전체 (35 tests)
pytest tests/unit         # 유닛만
pytest -k "quest"         # 퀘스트 관련만
pytest --cov=agent_society
```

---

## LLM 백엔드 선택

| 백엔드 | 클래스 | 용도 |
|---|---|---|
| `MockNarrator` | 테스트용 stub | 빠른 개발·테스트 |
| `HuggingFaceNarrator` | `google/gemma-4-E4B-it` 로컬 추론 | 실제 서사 생성 |
| `OllamaNarrator` | Ollama `/api/chat` | Ollama 서버 사용 시 |

```python
from agent_society.llm import HuggingFaceNarrator, MockNarrator
from agent_society.quests import QuestGenerator

# 실제 LLM
quest_gen = QuestGenerator(HuggingFaceNarrator())

# 테스트용 (LLM 없이)
quest_gen = QuestGenerator(MockNarrator())
```

---

## 관련 문서

| 문서 | 내용 |
|---|---|
| `PLAN.md` | 마일스톤 현황 (M1 완료, M2 완료, M3 완료) |
| `ARCHITECTURE.md` | 코드 경계, tick 순서, write 권한 규칙 |
| `CLAUDE.md` | AI 코드 작성 가이드라인 |
| `docs/research/` | 선행 연구 조사 문서 |
