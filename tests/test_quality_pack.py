from pathlib import Path

from src.feedback import FeedbackStore
from src.schemas import PlanOutput, ReflectOutput, RerankOutput


def test_plan_schema_valid():
    p = PlanOutput(sub_questions=["q1", "q2", "q3"])
    assert p.sub_questions == ["q1", "q2", "q3"]


def test_reflect_schema_defaults_gaps_empty():
    r = ReflectOutput(sufficient=True)
    assert r.gaps == []


def test_rerank_schema_accepts_floats():
    r = RerankOutput(scores=[1.5, 9.0, 5])
    assert r.scores == [1.5, 9.0, 5.0]


def test_feedback_submit_and_latest(tmp_path: Path):
    fb = FeedbackStore(tmp_path / "fb.sqlite")
    fb.submit("T1", rating=1, comment="great", topic="LangGraph")
    fb.submit("T1", rating=-1, comment="bad after edit", topic="LangGraph")
    latest = fb.latest_for("T1")
    assert latest["rating"] == -1
    assert latest["comment"] == "bad after edit"


def test_feedback_stats_counts_pos_neg(tmp_path: Path):
    fb = FeedbackStore(tmp_path / "fb.sqlite")
    fb.submit("A", 1)
    fb.submit("B", -1)
    fb.submit("C", 1)
    s = fb.stats()
    assert s["total"] == 3
    assert s["positive"] == 2
    assert s["negative"] == 1


def test_langsmith_status_disabled_when_no_env(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    from src.llm import langsmith_status

    s = langsmith_status()
    assert s["enabled"] is False
    assert s["has_key"] is False


def test_langsmith_status_enabled_with_env(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls__test123")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "my-proj")
    from src.llm import langsmith_status

    s = langsmith_status()
    assert s["enabled"] is True
    assert s["project"] == "my-proj"
    assert "my-proj" in s["url"]


def test_plan_node_text_path_still_works():
    from src.nodes.plan import plan_node
    from tests.conftest import make_fake_llm

    llm = make_fake_llm(['{"sub_questions": ["a", "b", "c"]}'])
    out = plan_node({"topic": "X", "num_questions": 3}, llm=llm)
    assert out["sub_questions"] == ["a", "b", "c"]


def test_reflect_node_text_path_still_works():
    from src.nodes.reflect import reflect_node
    from tests.conftest import make_fake_llm

    llm = make_fake_llm(['{"sufficient": true, "gaps": []}'])
    out = reflect_node({"topic": "X", "summaries": ["s"], "iteration": 1}, llm=llm)
    assert out["sufficient"] is True
