"""OllamaNarrator — Ollama /api/chat 기반 QuestNarrator 구현체.

참조: docs/research/04_local_llm_hardware.md
- 모델: gemma4:e4b (E4B Q8_K_XL 권장, 8.66 GB) or gemma4:e4b-q4_0 (dev)
- thinking 비활성화: 시스템 프롬프트에 <|think|> 토큰 미삽입
- CUDA 12.x 계열 필수 (13.2 사용 시 출력 품질 저하)
- /api/chat 사용 (chat template 자동 처리)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from agent_society.llm.mock_backend import MockNarrator
from agent_society.llm.prompts import build_prompt

if TYPE_CHECKING:
    from agent_society.quests.context import QuestContext

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
OLLAMA_CHAT_PATH = "/api/chat"


class OllamaNarrator:
    """Calls Ollama's /api/chat endpoint to generate quest narratives.

    narrate(intent, context) 시그니처에서:
    - intent: QuestIntent (quest_type, target, urgency, supporters, reward)
    - context: QuestContext (다수 agent needs + 활성 이벤트 + scarcity 맵)

    두 객체를 prompts.build_prompt()로 조립해 LLM에 전달.
    실패 시 MockNarrator fallback.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "gemma4:e4b",
        temperature: float = 0.8,
        top_p: float = 0.95,
        top_k: int = 64,
        max_tokens: int = 200,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._url = host.rstrip("/") + OLLAMA_CHAT_PATH
        self._model = model
        self._options: dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "num_predict": max_tokens,
            # Gemma 4 chat template 종료자
            "stop": ["<turn|>", "<|turn>user"],
        }
        self._timeout = timeout
        self._fallback = MockNarrator()

    def narrate(self, intent: object, context: QuestContext | None = None) -> str:
        intent_summary = _intent_to_summary(intent)
        prompt = build_prompt(intent_summary, context)

        try:
            return self._call(prompt)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            log.warning("Ollama unreachable (%s) — using MockNarrator fallback", e)
            return self._fallback.narrate(intent, context)
        except OllamaError as e:
            log.warning("Ollama error: %s — using MockNarrator fallback", e)
            return self._fallback.narrate(intent, context)

    def _call(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": self._options,
        }
        resp = httpx.post(self._url, json=payload, timeout=self._timeout)
        if resp.status_code != 200:
            raise OllamaError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        try:
            text: str = data["message"]["content"].strip()
        except (KeyError, TypeError) as e:
            raise OllamaError(f"Unexpected response shape: {data}") from e

        if not text:
            raise OllamaError("Empty response from model")

        log.debug("OllamaNarrator: %d chars generated", len(text))
        return text

    def is_available(self) -> bool:
        """Ollama 서버 도달 가능 여부 확인."""
        try:
            resp = httpx.get(
                self._url.replace(OLLAMA_CHAT_PATH, "/api/tags"),
                timeout=3.0,
            )
            return resp.status_code == 200
        except Exception:
            return False


class OllamaError(Exception):
    pass


def _intent_to_summary(intent: object) -> str:
    """QuestIntent (또는 임의 객체)를 한 줄 요약 문자열로 변환."""
    parts = []
    for attr in ("quest_type", "target", "urgency", "supporters", "reward"):
        val = getattr(intent, attr, None)
        if val is not None:
            parts.append(f"{attr}={val!r}")
    return ", ".join(parts) if parts else repr(intent)
