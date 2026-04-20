# 04. Local LLM — 하드웨어·모델 선택 (v0.2)

> v0.2 변경: 일반 가이드 → **구체 repo·파일·다운로드 명령·함정**까지 반영.
> 타겟 하드웨어: **RTX 5060 (16GB VRAM)**, Blackwell, FP4 native.

---

## 1. 결론 — 바로 쓸 모델

| 우선순위 | Repo | 파일 | 크기 | 용도 |
|---|---|---|---|---|
| **★ 메인** | `unsloth/gemma-4-E4B-it-GGUF` | `gemma-4-E4B-it-UD-Q8_K_XL.gguf` | **8.66 GB** | Quest 서사화 기본 |
| 경량 (dev) | 동일 repo | `gemma-4-E4B-it-Q4_K_M.gguf` | 4.98 GB | 빠른 iteration, 프롬프트 튜닝 |
| 품질 업그레이드 후보 | `unsloth/gemma-4-26B-A4B-it-GGUF` | `gemma-4-26B-A4B-it-UD-Q3_K_M.gguf` | 12.5 GB | E4B 한국어 서사 품질 부족 시 |

- Unsloth repo URL 접두: `https://huggingface.co/`
- E4B 메인 페이지: https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF
- 26B-A4B 메인 페이지: https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF

### 왜 Unsloth repo인가

Gemma 4 GGUF를 올리는 곳은 여럿이나 **Unsloth(danielhanchen)가 사실상 표준**:
- Dynamic 2.0 양자화 적용 (imatrix 캘리브레이션 최신)
- Google 공식 chat template + llama.cpp 수정 반영
- 업데이트 빠름

### 왜 E4B Q8부터인가

- Unsloth 공식 권장: **small 모델은 8-bit, large 모델은 Dynamic 4-bit부터 시작**
- 16GB 중 모델이 8.66GB → **KV cache·context에 7GB 여유**
- Quest 서사 프롬프트는 페르소나·few-shot 포함 시 수천 토큰이라 context 여유가 중요
- 4B급 최고 품질 양자화 (Q8_K_XL은 거의 비손실)

---

## 2. VRAM 예산 상세

| 구성 | 모델 | KV cache (8K ctx) | 여유 |
|---|---|---|---|
| E4B Q4 | 5 GB | ~1.5 GB | ~9.5 GB (넉넉) |
| **E4B Q8 (권장)** | 8.7 GB | ~1.5 GB | ~5.8 GB (충분) |
| 26B-A4B Q3 | 12.5 GB | ~2 GB | ~1.5 GB (타이트) |
| 26B-A4B Q4_K_M | 16.9 GB | ~2 GB | **음수 → 불가** |
| 31B Q4 | 18–20 GB | — | **불가** |

**핵심**: 26B-A4B의 `Q4_K_M`·`UD-Q4_K_XL`은 **16GB에 들어가지 않는다**.
Unsloth 공식 수치로 4-bit 26B-A4B는 18GB 총 메모리 필요. 16GB에선 CPU offload
발생 → 속도 크게 저하. **16GB에서 26B-A4B는 Q3_K_M이 상한선**.

---

## 3. ⚠ 반드시 피할 것 (함정)

### 3.1 **CUDA 13.2 런타임은 GGUF 출력을 망가뜨린다**

Unsloth 공식 경고: *"Do NOT use CUDA 13.2 runtime for any GGUF as it will cause
poor outputs."* → CUDA 12.x 계열을 쓸 것. 12.4 또는 12.6 권장.

### 3.2 Thinking 모드는 Quest 서사에 비활성화

- Gemma 4는 `<|think|>` 토큰으로 chain-of-thought 제어
- 활성화 시 내부 추론이 출력에 섞여 **파싱이 꼬임**
- Quest 서사는 최종 출력만 필요 → **thinking=false 고정**
- 시스템 프롬프트에 `<|think|>` 토큰 미삽입이 비활성화 방법

### 3.3 Chat template 변경됨

Gemma 3 → Gemma 4에서 template이 바뀜. 직접 프롬프트 조립 시 주의:

```
<bos><|turn>system
...system prompt...<turn|>
<|turn>user
...user message...<turn|>
<|turn>model
```

Ollama·최신 llama.cpp는 자동 처리. Raw HTTP 호출 시 template을 서버에서
적용하도록 `/api/chat` 엔드포인트 사용 (Ollama) 또는 `chat/completions` 호환
엔드포인트 사용 권장.

### 3.4 31B·26B-A4B Q4 이상은 시도하지 말 것

16GB에선 오프로딩 발생 → 10배 이상 느려짐. 성능이 떨어지는 게 아니라
사용 불가 수준이 됨.

---

## 4. 다운로드 명령

### 4.1 huggingface-cli (권장)

```bash
pip install -U "huggingface_hub[cli]" hf_transfer
export HF_HUB_ENABLE_HF_TRANSFER=1

# 메인 선택
huggingface-cli download unsloth/gemma-4-E4B-it-GGUF \
  gemma-4-E4B-it-UD-Q8_K_XL.gguf \
  --local-dir ./models/gemma4-e4b

# 경량 대안
huggingface-cli download unsloth/gemma-4-E4B-it-GGUF \
  gemma-4-E4B-it-Q4_K_M.gguf \
  --local-dir ./models/gemma4-e4b

# 업그레이드 후보
huggingface-cli download unsloth/gemma-4-26B-A4B-it-GGUF \
  gemma-4-26B-A4B-it-UD-Q3_K_M.gguf \
  --local-dir ./models/gemma4-26b-a4b
```

### 4.2 Ollama (더 간단)

```bash
# 설치 후
ollama pull gemma4:e4b
# 또는 구체 quant 지정
ollama pull gemma4:e4b-q8_0
```

MVP 단계에선 Ollama가 관리 편리 (chat template·서버·API 자동). 프롬프트
튜닝이 끝나고 속도 최적화가 필요해지면 llama.cpp 직접 사용으로 전환.

### 4.3 llama.cpp (세밀한 제어 필요 시)

```bash
./build/bin/llama-cli \
  -m ./models/gemma4-e4b/gemma-4-E4B-it-UD-Q8_K_XL.gguf \
  -ngl 99 \           # 모든 레이어 GPU로
  -c 8192 \           # context
  -fa on \            # flash attention
  --temp 0.8
```

KV cache를 양자화하면 VRAM 더 절약:

```bash
# KV cache를 Q4_0로 (품질 약간 손실, VRAM 크게 절약)
./build/bin/llama-server \
  -m ./models/... \
  -ngl 99 -c 8192 -fa on \
  -ctk q4_0 -ctv q4_0
```

---

## 5. 프로젝트 설정에 반영 (config/default.yaml)

```yaml
llm:
  backend: ollama                       # 또는 llamacpp
  host: http://localhost:11434
  model: gemma4:e4b                     # Ollama 태그
  # llamacpp 직접 호출 시
  # model_path: ./models/gemma4-e4b/gemma-4-E4B-it-UD-Q8_K_XL.gguf
  temperature: 0.8
  top_p: 0.95
  top_k: 64
  max_tokens: 200
  enable_thinking: false                # 반드시 false
  stop:
    - "<turn|>"
    - "<|turn>user"
```

---

## 6. 권장 워크플로 (M5 단계에서 적용)

1. **Ollama 설치 + E4B Q8 pull** — 가장 빠른 PoC 경로
2. `llm/client.py` 구현 — Ollama `/api/chat` 호출, 실패 시 fallback
3. **샘플 Quest 20개로 수동 품질 평가** — 한국어 톤, 문맥 보존, 길이
4. 품질 OK → 그대로 확정
5. 품질 부족 (한국어 자연스러움·일관성 이슈) →
   - 먼저 **프롬프트·few-shot 개선** (ROI 가장 높음)
   - 그래도 부족 → 26B-A4B Q3로 A/B
   - 최후 수단 → Unsloth로 E4B QLoRA fine-tuning (16GB에서 가능)

---

## 7. Fine-tuning 고려사항 (MVP 이후)

E4B QLoRA는 **16GB VRAM에 충분히 들어간다** (Unsloth 수치: E4B LoRA 17GB,
Unsloth 최적화로 16GB 가능).

- 사용 시점: 특정 세계관 tone 고정 필요 시
- 데이터셋: Värtinen 2022의 978 퀘스트 공개 데이터셋 활용 가능
  (단, 한국어 스타일을 원하면 별도 구축 필요)
- 26B-A4B LoRA는 40GB+ 필요 → 클라우드에서만 가능

---

## 8. 한국어 품질 관련 경계점

- Gemma 4는 140+ 언어 지원하나 **한국어 창작 품질은 4B급에서 검증 필요**
- 영어 prompt + 한국어 output 지시로 생성 성능이 나아지는 경우 있음
- 한국어 few-shot 예제 2–3개 제공 시 일관성 크게 상승
- MVP 평가 시 다음 기준 체크:
  - [ ] 자연스러운 한국어 구어체 (번역투 없음)
  - [ ] Quest 구조(목표·보상) 정보 보존
  - [ ] 의뢰자 페르소나 반영 (말투 차이)
  - [ ] 2–4문장 길이 준수

기준 실패 시 프롬프트 개선 → 26B-A4B 전환 → QLoRA 순으로 upgrade.

---

## 9. 체크리스트 (M5 진입 시)

- [ ] CUDA 런타임 버전 확인 (12.x 계열인지 — **13.2 아님**)
- [ ] Ollama 설치 및 `ollama run gemma4:e4b` 동작 확인
- [ ] E4B Q8 GGUF 다운로드 완료 (8.66 GB)
- [ ] 첫 번째 샘플 요청으로 latency 측정 (목표 < 3초 @ 200 tokens)
- [ ] `enable_thinking: false`가 실제 출력에 반영되는지 확인
- [ ] fallback 템플릿 파일 준비 (`config/prompts/fallback_*.txt`)

---

## 참조

- Unsloth 공식 가이드: https://unsloth.ai/docs/models/gemma-4
- Gemma 4 E4B GGUF: https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF
- Gemma 4 26B-A4B GGUF: https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF
- Ollama 모델 카탈로그: https://ollama.com/library/gemma4