"""A/B comparison utility — runs the graph twice with different option sets
and judges both reports to declare a winner."""

import uuid
from typing import Any

from src.graph import build_graph
from src.judge import judge_report
from src.multi_agent import build_multi_agent_graph
from src.state import empty_state


def _make_graph(use_multi_agent: bool, **kwargs):
    if use_multi_agent:
        return build_multi_agent_graph(**kwargs)
    return build_graph(**kwargs)


def run_one(
    topic: str,
    options: dict[str, Any],
    *,
    checkpointer=None,
    search_cache=None,
    thread_id: str | None = None,
) -> dict:
    """Run the graph once with given options, return final state values."""
    multi = bool(options.pop("multi_agent_mode", False))
    use_critic = bool(options.pop("use_critic", False))

    graph = _make_graph(
        multi,
        checkpointer=checkpointer,
        search_cache=search_cache,
        use_critic=use_critic if not multi else False,
    )
    config = {"configurable": {"thread_id": thread_id or uuid.uuid4().hex[:8]}}
    state = empty_state(topic, **options)
    graph.invoke(state, config=config)
    return graph.get_state(config).values or {}


def judge_pair(
    topic: str,
    state_a: dict,
    state_b: dict,
    language: str = "en",
) -> dict:
    """Judge both reports and return scores + verdict."""
    rep_a = state_a.get("final_report") or ""
    rep_b = state_b.get("final_report") or ""

    score_a = judge_report(topic, rep_a, language) if rep_a else None
    score_b = judge_report(topic, rep_b, language) if rep_b else None

    a_overall = float(score_a.overall) if score_a else 0.0
    b_overall = float(score_b.overall) if score_b else 0.0

    if a_overall > b_overall + 0.5:
        winner = "A"
    elif b_overall > a_overall + 0.5:
        winner = "B"
    else:
        winner = "tie"

    return {
        "winner": winner,
        "score_a": score_a.model_dump() if score_a else None,
        "score_b": score_b.model_dump() if score_b else None,
        "diff": round(a_overall - b_overall, 2),
    }


# Each preset has localized label + description + plain-language tags
# (speed, cost, recommended use case) so non-experts can pick confidently.
PRESETS = {
    "default": {
        "label": {
            "ko": "🚀 기본 — 빠르고 단순",
            "en": "🚀 Basic — Fast & simple",
        },
        "description": {
            "ko": "추가 기능 모두 끔. LLM 호출이 가장 적고 가장 빠릅니다. 가벼운 주제 / 빠른 확인용.",
            "en": "All extras off. Fewest LLM calls, fastest run. Best for light topics or quick checks.",
        },
        "tags": {
            "ko": "⚡ 가장 빠름 · 💰 가장 저렴 · 🎯 일반 주제",
            "en": "⚡ Fastest · 💰 Cheapest · 🎯 Everyday topics",
        },
        "options": {},
    },
    "rerank": {
        "label": {
            "ko": "🔍 검색 품질 강화 — 결과 재정렬 + 출처 다양화",
            "en": "🔍 Better Search — Re-rank hits + diverse sources",
        },
        "description": {
            "ko": "LLM이 검색 결과 관련도를 다시 점수 매기고, 같은 사이트 중복을 줄여 출처를 다양하게 만듭니다. 보고서 자체에는 손대지 않습니다.",
            "en": "LLM re-scores hit relevance and avoids letting one site (e.g. reddit) dominate. The report itself is unchanged.",
        },
        "tags": {
            "ko": "⏱ 약간 느림 · 💰 LLM +N회 · 🎯 출처 신뢰도 중요할 때",
            "en": "⏱ Slightly slower · 💰 +N LLM calls · 🎯 When source quality matters",
        },
        "options": {
            "rerank": True,
            "domain_dedup": True,
            "max_per_domain": 2,
        },
    },
    "self_correct": {
        "label": {
            "ko": "✅ 보고서 신뢰도 강화 — 자가 교정 + 출처 검증",
            "en": "✅ Trustworthy Report — Self-correct + Citation check",
        },
        "description": {
            "ko": "초안 작성 후 에디터 LLM이 검토해 약점이 있으면 1회 재작성하고, 각 주장이 어떤 출처로 뒷받침되는지 분석합니다. 학술/리서치 용도에 적합.",
            "en": "After the first draft, an editor LLM reviews and rewrites once if needed, and each claim is mapped to its supporting sources. Great for academic / research use.",
        },
        "tags": {
            "ko": "⏱ 보통 · 💰 LLM +2~3회 · 🎯 정확성 / 인용이 중요할 때",
            "en": "⏱ Moderate · 💰 +2-3 LLM calls · 🎯 When accuracy & citations matter",
        },
        "options": {
            "self_correct_writer": True,
            "cross_reference_check": True,
        },
    },
    "multi_agent": {
        "label": {
            "ko": "🤖 전문가 팀 모드 — Researcher · Critic · Writer 협업",
            "en": "🤖 Expert Team — Researcher · Critic · Writer agents",
        },
        "description": {
            "ko": "Supervisor가 세 전문 에이전트를 조율하고, 각자에게 가장 잘 맞는 모델 (예: Critic은 Groq Llama 70B, Writer는 Gemini 2.5)을 자동으로 배정합니다.",
            "en": "A Supervisor orchestrates three specialized agents and auto-assigns the best model per role (e.g. Groq Llama 70B for Critic, Gemini 2.5 for Writer).",
        },
        "tags": {
            "ko": "⏱ 보통 · 💰 LLM +수회 · 🎯 다양한 관점이 필요할 때",
            "en": "⏱ Moderate · 💰 Several extra LLM calls · 🎯 When multiple perspectives help",
        },
        "options": {
            "multi_agent_mode": True,
            "per_agent_models": True,
        },
    },
    "max_quality": {
        "label": {
            "ko": "🏆 최고 품질 — 모든 기능 ON",
            "en": "🏆 Maximum Quality — Everything on",
        },
        "description": {
            "ko": "전문가 팀 + 검색 품질 강화 + 자가 교정 + 출처 검증 모두 켭니다. 가장 정밀한 보고서를 만들지만 시간과 LLM 비용이 가장 큽니다.",
            "en": "Expert team + better search + self-correct + citation check, all enabled. Most polished report, but slowest and most expensive.",
        },
        "tags": {
            "ko": "🐢 가장 느림 · 💰💰 LLM +다수 · 🎯 발표 / 외부 공유용",
            "en": "🐢 Slowest · 💰💰 Many extra LLM calls · 🎯 For polished / public output",
        },
        "options": {
            "multi_agent_mode": True,
            "per_agent_models": True,
            "rerank": True,
            "domain_dedup": True,
            "max_per_domain": 2,
            "self_correct_writer": True,
            "cross_reference_check": True,
        },
    },
}


def preset_label(key: str, lang: str = "en") -> str:
    p = PRESETS.get(key, {})
    label = p.get("label", "")
    if isinstance(label, dict):
        return label.get(lang) or label.get("en") or key
    return label or key


def preset_description(key: str, lang: str = "en") -> str:
    p = PRESETS.get(key, {})
    desc = p.get("description", "")
    if isinstance(desc, dict):
        return desc.get(lang) or desc.get("en") or ""
    return desc or ""


def preset_tags(key: str, lang: str = "en") -> str:
    p = PRESETS.get(key, {})
    tags = p.get("tags", "")
    if isinstance(tags, dict):
        return tags.get(lang) or tags.get("en") or ""
    return tags or ""
