"""HuggingFaceNarrator — transformers 로컬 추론 기반 QuestNarrator 구현체.

모델: google/gemma-4-E4B-it (기본값)
사전 조건: pip install transformers torch accelerate
huggingface-cli login 또는 HF_TOKEN 환경변수로 인증 필요.

enable_thinking=False: 시스템 프롬프트에 thinking 토큰 미삽입.
실패 시 MockNarrator fallback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_society.llm.mock_backend import MockNarrator
from agent_society.llm.prompts import SYSTEM_PROMPT, build_prompt

if TYPE_CHECKING:
    from agent_society.quests.context import QuestContext

log = logging.getLogger(__name__)

DEFAULT_MODEL = "google/gemma-4-E4B-it"


class HuggingFaceNarrator:
    """google/gemma-4-E4B-it (또는 호환 모델)로 quest 서술을 생성한다.

    첫 narrate() 호출 시 모델을 lazy-load한다 (초기 시작 지연 최소화).
    실패 시 MockNarrator fallback.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = 1.0,
        top_p: float = 0.95,
        top_k: int = 64,
        max_new_tokens: int = 200,
        device_map: str = "auto",
    ) -> None:
        self._model_id = model
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._max_new_tokens = max_new_tokens
        self._device_map = device_map
        self._fallback = MockNarrator()

        # lazy-loaded
        self._processor: Any = None
        self._model: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import AutoModelForCausalLM, AutoProcessor
        except ImportError as e:
            raise ImportError(
                "transformers 패키지가 필요합니다: pip install transformers torch accelerate"
            ) from e

        log.info("모델 로딩 중: %s", self._model_id)
        self._processor = AutoProcessor.from_pretrained(self._model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_id,
            dtype="auto",
            device_map=self._device_map,
        )
        log.info("모델 로딩 완료")

    def narrate(self, intent: object, context: "QuestContext | None" = None) -> str:
        user_prompt = build_prompt(_intent_to_summary(intent), context)
        try:
            self._load()
            return self._call(user_prompt)
        except Exception as e:
            log.warning("HuggingFace Narrator 오류 (%s) — MockNarrator fallback 사용", e)
            return self._fallback.narrate(intent, context)

    def _call(self, user_prompt: str) -> str:
        import torch

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_prompt},
        ]
        text = self._processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = self._processor(text=text, return_tensors="pt").to(self._model.device)
        input_len: int = inputs["input_ids"].shape[-1]

        with torch.inference_mode():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=self._max_new_tokens,
                temperature=self._temperature,
                top_p=self._top_p,
                top_k=self._top_k,
                do_sample=True,
            )

        generated = outputs[0][input_len:]
        response = self._processor.decode(generated, skip_special_tokens=True).strip()

        if not response:
            raise ValueError("모델이 빈 응답을 반환했습니다")

        log.debug("HuggingFaceNarrator: %d chars generated", len(response))
        return response


def _intent_to_summary(intent: object) -> str:
    parts = []
    for attr in ("quest_type", "target", "urgency", "supporters", "reward"):
        val = getattr(intent, attr, None)
        if val is not None:
            parts.append(f"{attr}={val!r}")
    return ", ".join(parts) if parts else repr(intent)
