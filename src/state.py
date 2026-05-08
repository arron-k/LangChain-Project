import operator
from typing import Annotated, TypedDict


class ResearchState(TypedDict, total=False):
    topic: str
    language: str
    num_questions: int
    sub_questions: list[str]
    search_results: Annotated[list[dict], operator.add]
    summaries: Annotated[list[str], operator.add]
    iteration: int
    max_iterations: int
    sufficient: bool
    reflection: str
    critique: str
    final_report: str
    report_style: str
    report_length: str
    include_domains: list[str]
    exclude_domains: list[str]
    time_range: str
    rerank: bool
    min_hit_score: float
    use_critic: bool
    extract_top: bool
    use_lessons: bool
    self_rag: bool
    multi_agent: bool
    domain_dedup: bool
    max_per_domain: int
    freshness_max_age_days: int
    per_agent_models: bool
    llm_supervisor: bool
    persona: str
    follow_up: str


DEFAULTS = {
    "language": "en",
    "num_questions": 3,
    "max_iterations": 3,
    "report_style": "concise",
    "report_length": "medium",
    "include_domains": [],
    "exclude_domains": [],
    "time_range": "",
    "rerank": False,
    "min_hit_score": 0.0,
    "use_critic": False,
    "extract_top": False,
    "use_lessons": False,
    "self_rag": False,
    "multi_agent": False,
    "domain_dedup": False,
    "max_per_domain": 2,
    "freshness_max_age_days": 0,
    "per_agent_models": False,
    "llm_supervisor": False,
    "persona": "",
}


def empty_state(topic: str, **overrides) -> ResearchState:
    state: ResearchState = {
        "topic": topic,
        "sub_questions": [],
        "search_results": [],
        "summaries": [],
        "iteration": 0,
        "sufficient": False,
        "reflection": "",
        "critique": "",
        "final_report": "",
        "follow_up": "",
        **DEFAULTS,
    }
    state.update(overrides)
    return state
