# 04. Local LLM — 하드웨어·모델 선택

타겟 하드웨어: **RTX 5060 (16GB VRAM)**, Blackwell 아키텍처, 5세대 텐서 코어,
native FP4 지원.

---

## 4.1 후보 모델 정리 (Gemma 계열)

### Gemma 3 4B

- Google의 vision-language model (멀티모달 지원)
- Decoder-only Transformer, 5:1 local sliding window + global attention
  interleaving
- KV-cache 효율 → 긴 context 가능
- GGUF Q4 기준 ~3–4GB VRAM. 16GB에는 여유

### Gemma 4 E4B

- 경량 엣지 변종 (enhanced 4B)
- 6–12GB 하드웨어에도 쾌적
- GGUF Q4_K_M / Q5로 로드

### Gemma 4 26B-A4B (MoE)

- 총 26B 파라미터, inference 시 활성 3.8B (Mixture-of-Experts)
- **Q4_K_M 기준 ~15GB, 16GB GPU에 fit**
- 16GB GPU(5060 Ti 등)에서 40–50 tok/s 기대
- **Gemma 4 계열에서 품질 vs VRAM의 sweet spot**

### Gemma 4 31B Dense

- 최고 품질. Q4에도 ~18GB+ 요구 → 16GB로는 타이트
- 본 프로젝트 범위 밖 (필요하면 24GB 카드 고려)

---

## 4.2 선택 가이드

| 단계 | 모델 | 이유 |
|---|---|---|
| **MVP / 반복 빠른 개발** | Gemma 3 4B 또는 Gemma 4 E4B (Q4_K_M) | 빠름, 메모리 여유 |
| **품질 요구 상승 시** | Gemma 4 26B-A4B MoE (Q4_K_M) | 16GB fit, 활성 파라미터 적어 속도 유지 |
| **품질 최대화** | Gemma 4 31B dense | 16GB로는 부담. 고려 보류 |

**권장**: MVP는 4B로 시작 → Quest 서사 품질 평가 → 부족하면 26B MoE로 승격.

---

## 4.3 추론 스택

- **Ollama** — 가장 간단. `ollama run gemma4:e4b` 식. GGUF 자동 관리
- **llama.cpp** — 세밀한 제어, 배치 추론
- **Unsloth** — fine-tuning 필요 시 메모리 효율 최고 (QLoRA 80% VRAM 절감 실측
  사례 있음)
- **vLLM** — 고throughput 서빙. 우리 규모에는 과함

**초안 선택**: Ollama + Python `requests` 호출. 추후 latency 이슈 발생 시
llama.cpp로 스위치.

---

## 4.4 VRAM 예산 설계

16GB 중:

- 모델 로드: 4–8GB (4B Q4) / ~15GB (26B MoE Q4)
- KV cache (context window): 1–4GB (context 길이 따라)
- 시스템/기타: ~0.5GB

Quest 생성 시 context는 크지 않다 (에이전트 페르소나 + 상황 + 목표 ≈ 수천
토큰). **4B + 8K context = 매우 여유로움.** 26B MoE 선택 시 context 8K에서
fit은 되지만 타이트 — 4K로 줄이거나 더 짧은 프롬프트 설계 필요.

---

## 4.5 추론 호출 패턴 (설계 초안)

```python
# Pseudocode
class QuestNarrator:
    def __init__(self, model="gemma4:e4b"):
        self.client = OllamaClient(model)

    def narrate(self, quest_intent: QuestIntent, context: WorldContext) -> str:
        prompt = self.build_prompt(quest_intent, context)
        # stream=False for simplicity, switch to stream when UI ready
        response = self.client.generate(prompt, temperature=0.8, max_tokens=200)
        return self.validate_and_clean(response, quest_intent)
```

### 성능 목표 (MVP)

- 평균 Quest 생성 latency: **< 3초 (4B)**, < 5초 (26B MoE)
- 동시 생성은 불필요 — Quest는 이벤트 발생 시점에 하나씩 생성
- 캐시 히트율 30%+ 확보 (구조 동일 Quest 재활용)

---

## 4.6 Fine-tuning 여부

**MVP에서는 불필요.** 이유:

- Gemma 4B/E4B는 instruction-following이 이미 강함
- In-context few-shot + 구조화된 prompt로 시작
- 데이터셋부터 만드는 건 시간 소모 큼

**추후 fine-tuning 고려 조건**:
- 특정 세계관 tone 고정 필요 시
- Quest-GPT (Värtinen 2022) 데이터셋 활용 가능

QLoRA로 4B 모델을 16GB GPU에서 fine-tuning 가능 — 기존 사례 다수.
