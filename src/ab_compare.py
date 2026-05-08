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


PRESETS = {
    "default": {
        "label": "Default (단순)",
        "description": "기본 그래프, 옵션 모두 OFF",
        "options": {},
    },
    "rerank": {
        "label": "+Rerank + Domain Dedup",
        "description": "검색 품질만 강화",
        "options": {
            "rerank": True,
            "domain_dedup": True,
            "max_per_domain": 2,
        },
    },
    "self_correct": {
        "label": "+Self-correct + Cross-ref",
        "description": "보고서 자가 교정 + 출처 검증",
        "options": {
            "self_correct_writer": True,
            "cross_reference_check": True,
        },
    },
    "multi_agent": {
        "label": "Multi-agent + Per-agent models",
        "description": "Supervisor + 에이전트별 모델",
        "options": {
            "multi_agent_mode": True,
            "per_agent_models": True,
        },
    },
    "max_quality": {
        "label": "최고 품질 (모든 옵션)",
        "description": "Multi-agent + Critic + Self-correct + Cross-ref + Rerank + Dedup",
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
