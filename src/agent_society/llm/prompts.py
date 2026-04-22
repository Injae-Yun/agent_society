"""Quest narration prompt templates and few-shot examples (Korean).

QuestContext(다수 agent needs + 활성 이벤트 + scarcity)를 한국어 bullet으로
변환해 few-shot 예제와 함께 LLM에 전달한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_society.quests.context import QuestContext

# ── System prompt ─────────────────────────────────────────────────────────────
# enable_thinking=false: <|think|> 토큰 미삽입
SYSTEM_PROMPT = """\
당신은 중세 판타지 RPG의 Quest 서술자입니다.
주어진 QuestIntent(목표·지원자·보상)와 월드 현황(agent 욕구·이벤트·물가)을 바탕으로
플레이어가 수락할 Quest 본문을 작성하세요.

규칙:
- 2~4문장, 자연스러운 한국어 구어체
- 의뢰자 페르소나(직업·상황)를 말투에 반영
- 목표와 보상 정보를 반드시 포함
- 번역투·문어체 금지
- 월드 현황에 나타난 구체적인 위기(기근·도로 붕괴·약탈 등)를 서사에 녹여낼 것
"""

# ── Few-shot 예제 ─────────────────────────────────────────────────────────────
FEW_SHOT_EXAMPLES = [
    {
        "intent": "quest_type=raider_suppress, target=raider.hideout, urgency=0.85, supporters=['merchant_1','herder_2']",
        "context": (
            "계절: Summer / "
            "긴급 needs: [merchant_1 Alice(safety=0.90, city), herder_2 Kay(safety=0.75, farm)] / "
            "이벤트: RaidAttempt(route.risky.3, plundered) / "
            "scarcity: wheat=0.08, meat=0.12"
        ),
        "narrative": (
            "상인 앨리스가 다급하게 말을 건다. "
            "\"저번에 또 당했어요—짐수레 절반이 털렸고, 이번 여름 내내 위험 루트를 못 쓰겠어요. "
            "도적단 본거지를 쳐서 그놈들 기세를 꺾어 주시면 밀·고기 20개씩 드리겠습니다. "
            "목동 케이도 돕겠다고 했으니 같이 가면 어떨까요?\""
        ),
    },
    {
        "intent": "quest_type=road_restore, target=edge(city→farm), urgency=0.72, supporters=['farmer_3']",
        "context": (
            "계절: Autumn / "
            "긴급 needs: [farmer_3 Cam(hunger=0.78, farm), cook_1 Nara(tool_need=0.74, city)] / "
            "이벤트: RoadCollapse(city↔farm) / "
            "scarcity: wheat=0.25, meat=0.18"
        ),
        "narrative": (
            "농부 캠이 한숨을 쉬며 말한다. "
            "\"이번 가을 수확은 잘 됐는데 도시로 내다 팔 길이 막혀버렸어요—다리가 무너졌거든요. "
            "요리사 나라도 재료가 없어 고생 중이라더군요. "
            "수리 재료만 갖다 주시면 제가 고쳐볼게요, 광석 5개 드리겠습니다.\""
        ),
    },
    {
        "intent": "quest_type=bulk_delivery, target=ore, urgency=0.60, supporters=['blacksmith_1']",
        "context": (
            "계절: Spring / "
            "긴급 needs: [blacksmith_1 Hira(tool_need=0.82, city), miner_1 Sam(hunger=0.65, farm)] / "
            "이벤트: (없음) / "
            "scarcity: ore=0.45, sword=0.60"
        ),
        "narrative": (
            "대장장이 히라가 망치를 내려놓으며 말한다. "
            "\"봄인데 광석이 벌써 바닥났어요—주문은 밀려드는데. "
            "광산에서 광석 15개만 가져다 주시면 무기 한 자루 만들어 드리겠습니다.\""
        ),
    },
]


# ── Prompt assembler ──────────────────────────────────────────────────────────

def build_prompt(intent_summary: str, context: QuestContext | None) -> str:
    """QuestIntent + QuestContext → LLM에 보낼 완성 프롬프트."""
    parts = [SYSTEM_PROMPT.strip(), ""]

    # Few-shot 예제
    parts.append("=== 예시 ===")
    for ex in FEW_SHOT_EXAMPLES:
        parts.append(f"[Intent] {ex['intent']}")
        parts.append(f"[Context] {ex['context']}")
        parts.append(f"[Quest] {ex['narrative']}")
        parts.append("")

    # 실제 월드 현황 (context)
    if context is not None:
        ctx_lines = _format_context(context)
        parts.append("=== 현재 월드 현황 ===")
        parts.extend(ctx_lines)
        parts.append("")

    # 실제 요청
    parts.append("=== 요청 ===")
    parts.append(f"[Intent] {intent_summary}")
    if context is not None:
        parts.append(f"[Context] {_context_one_liner(context)}")
    parts.append("[Quest]")

    return "\n".join(parts)


def _format_context(ctx: QuestContext) -> list[str]:
    """QuestContext를 읽기 쉬운 한국어 bullet 목록으로 변환."""
    lines: list[str] = []

    lines.append(f"- 현재 시각: tick={ctx.tick}, 계절={ctx.season}")

    if ctx.urgent_agents:
        lines.append(f"- 긴급 needs ({len(ctx.urgent_agents)}명):")
        for info in ctx.urgent_agents[:10]:  # 최대 10명 (프롬프트 길이 제한)
            need_kr = _need_kr(info.need_type.value)
            lines.append(
                f"    • {info.name} ({info.role}, {info.location}): "
                f"{need_kr} {info.urgency:.0%}"
            )
        if len(ctx.urgent_agents) > 10:
            lines.append(f"    … 외 {len(ctx.urgent_agents) - 10}명 추가")
    else:
        lines.append("- 긴급 needs: 없음")

    if ctx.active_event_summaries:
        lines.append("- 진행 중 이벤트: " + ", ".join(ctx.active_event_summaries[:5]))

    if ctx.scarcity_map:
        scarce = {k: v for k, v in ctx.scarcity_map.items() if v > 0.05}
        if scarce:
            scarcity_str = ", ".join(f"{k}={v:.3f}" for k, v in sorted(scarce.items(), key=lambda x: -x[1]))
            lines.append(f"- 재화 부족도(높을수록 희소): {scarcity_str}")

    if ctx.supporter_personas:
        lines.append("- 의뢰 지지자: " + ", ".join(ctx.supporter_personas))

    return lines


def _context_one_liner(ctx: QuestContext) -> str:
    """Few-shot 스타일의 한 줄 context 요약."""
    urgent_str = ", ".join(
        f"{i.name}({_need_kr(i.need_type.value)}={i.urgency:.2f}, {i.location})"
        for i in ctx.urgent_agents[:5]
    )
    events_str = ", ".join(ctx.active_event_summaries[:3]) or "없음"
    scarce_str = ", ".join(
        f"{k}={v:.3f}" for k, v in list(ctx.scarcity_map.items())[:4]
    )
    return (
        f"계절: {ctx.season} / "
        f"긴급 needs: [{urgent_str}] / "
        f"이벤트: {events_str} / "
        f"scarcity: {scarce_str}"
    )


_NEED_KR = {
    "hunger": "허기",
    "food_satisfaction": "식욕만족",
    "tool_need": "도구부족",
    "safety": "안전",
}


def _need_kr(need: str) -> str:
    return _NEED_KR.get(need, need)
