# 02. Quest Generation — 선행 연구

본 프로젝트의 System 3 (Quest Generator) 설계 참고 문헌.

---

## 2.1 Värtinen, Hämäläinen et al. (IEEE ToG, 2022) — Quest-GPT-2/3

*Generating Role-Playing Game Quests With GPT Language Models*
IEEE Transactions on Games, DOI 10.1109/TG.2022.3228480

### 핵심

- 6개 상용 RPG에서 978개 퀘스트·설명문 수집 후 공개 데이터셋화
- GPT-2를 fine-tuning, GPT-3도 실험
- 349명 사용자 평가, 500개 퀘스트 설명
- 고유명사·숫자를 placeholder로 치환하는 등 fine-tuning 포맷 최적화 mini-study

### 결과 (주목)

사람이 "받아들일 만하다"고 판단한 퀘스트 설명은 **5개 중 1개 꼴**. 개별 퀘스트
품질 편차가 큼.

### 본 프로젝트 시사점

**LLM에 raw prompt로 "퀘스트 써줘" 하면 평범해진다.** 반드시 월드 상태 + 에이전트
상태를 구조화된 컨텍스트로 넣어야 한다. 이 논문의 실패 지점이 우리의 출발점:
"구조화된 욕구·상황을 LLM에게 먹이면 서사 품질이 올라간다"는 가설.

---

## 2.2 van Stegeren & Myśliwiec (FDG 2021) — GPT-2 WoW Quest

*Fine-tuning GPT-2 on annotated RPG quests for NPC dialogue generation*
ACM FDG 2021 | DOI 10.1145/3472538.3472595

### 핵심

- World of Warcraft 퀘스트 데이터로 GPT-2 fine-tuning
- 주석: 퀘스트 제목·목표로 태그, NPC 대화를 생성
- 저자들이 "authoring aid"로 포지셔닝 (AI Dungeon식 자동 생성이 아님)
- 코드·데이터셋 공개

### 본 프로젝트 시사점

- **Prompt 포맷의 참고 사례** — `<quest_title>...<objective>...<dialogue>...` 식
  구조화된 태깅
- 우리는 fine-tuning 대신 in-context prompting + few-shot으로 시작 가능

---

## 2.3 Ashby et al. (CHI 2023) — KG + LM Personalized Quest ★ 구조적으로 가장 근접

*Personalized Quest and Dialogue Generation in Role-Playing Games: A Knowledge
Graph- and Language Model-based Approach*
DOI 10.1145/3544548.3581441

### 핵심

- **Knowledge Graph**로 월드 엔티티·사실 관리
- LM이 KG 콘텐츠를 기반으로 퀘스트·대화 생성 (mixed-initiative co-creativity)
- 장르 관습으로 제약된 PCG + 플레이어 입력 반응
- 3가지 방법 비교 (KG-based, 수작업 WoW, n-gram baseline)
- 판타지 RPG 맥락에서 playtest

### 본 프로젝트 시사점

**본 프로젝트와 아키텍처적으로 가장 유사.** 차이점:

- Ashby의 KG는 정적인 세계 사실 중심
- 본 프로젝트는 **"동적인 에이전트 needs/상태"**가 KG 대신 들어간다
- 즉 **Agent Society 상태 = Quest generator의 structured context**

이 논문의 prompt assembly 방식(KG 서브그래프를 템플릿에 삽입 → LM 호출)을
그대로 차용 가능.

---

## 2.4 Doran & Parberry (2011) — 구조 기반 Quest 분류

*A Prototype Quest Generator Based on a Structural Analysis of RPG Quests*
Proceedings of PCG 2011

### 핵심

- EverQuest, WoW, EVE Online, Vanguard 750+ 퀘스트 분석
- 퀘스트의 공통 **구조(structure)** 추출 → 분류 체계 → 생성기
- LLM 이전 시대의 **symbolic quest generation**

### 본 프로젝트 시사점

Quest의 **골격(goal, precondition, action chain, reward)**은 symbolic
구조로 먼저 생성하고, **자연어 서술만 LLM**이 담당하는 분업이 합리적.
이 논문의 분류표는 우리의 Quest type taxonomy 초안에 바로 쓸 수 있음.

---

## 2.5 그 외 참고할 갈래

- **Ammanabrolu, Riedl 등** (text-adventure) — Markov model, 신경망 퀘스트 생성
- **Minecraft GPT-4 minigame 논문** — LLM NPC와 사람이 협력해 퀘스트 수행.
  Collaborative behavior의 emergent pattern 관찰
- **LLM-RL 결합 (RLGDG)** — SFT 후 RL로 fine-tuning, 퀘스트 품질 개선
- **Procedural side-quest generation (최근 연구)** — sidequest를
  machine-readable format으로 직접 생성하려는 시도

---

## 2.6 설계 결정 초안

1. **Quest는 symbolic 구조 + LLM 서사화의 이층 구조**로 간다
   - 상층: `QuestIntent` (goal, target_need, actors, location_chain, reward)
   - 하층: LLM이 이 구조를 평어문 Quest로 번역
2. **Prompt context** 구성:
   - 발원 에이전트 페르소나·최근 memory
   - 관련 월드 상태(위치·이벤트)
   - Quest 구조(목표·보상)
   - Few-shot 예제 2–3개
3. **캐싱**: 같은 symbolic 구조는 변형만 달리해 재활용
4. **품질 게이트**: 생성 결과가 구조(goal/reward)를 보존하는지 경량 검증
   (rule-based regex 또는 별도 zero-shot check)
