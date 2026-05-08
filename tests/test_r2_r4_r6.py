from datetime import datetime, timedelta, timezone

from src.multi_agent import _deterministic_supervisor, build_multi_agent_graph
from src.nodes.search import _filter_by_freshness, search_node
from src.state import empty_state
from tests.conftest import make_fake_llm


def _iso(days_ago: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def test_freshness_drops_old_results():
    hits = [
        {"url": "u1", "published_date": _iso(10)},
        {"url": "u2", "published_date": _iso(400)},
        {"url": "u3", "published_date": _iso(2000)},
    ]
    out = _filter_by_freshness(hits, max_age_days=365)
    urls = [h["url"] for h in out]
    assert "u1" in urls
    assert "u2" not in urls
    assert "u3" not in urls


def test_freshness_keeps_undated_hits():
    hits = [
        {"url": "u1", "published_date": ""},
        {"url": "u2", "published_date": _iso(10)},
    ]
    out = _filter_by_freshness(hits, max_age_days=365)
    assert len(out) == 2


def test_freshness_falls_back_to_first_hit_if_all_filtered():
    hits = [
        {"url": "u1", "published_date": _iso(2000)},
        {"url": "u2", "published_date": _iso(3000)},
    ]
    out = _filter_by_freshness(hits, max_age_days=365)
    assert len(out) == 1


def test_search_node_passes_freshness_to_filter():
    def fake(q):
        return [
            {"url": "fresh", "content": "x", "score": 0.9, "published_date": _iso(30)},
            {"url": "old", "content": "x", "score": 0.9, "published_date": _iso(2000)},
        ]

    out = search_node(
        {"sub_questions": ["q"], "freshness_max_age_days": 365},
        search_fn=fake,
    )
    urls = [h["url"] for h in out["search_results"][0]["hits"]]
    assert "fresh" in urls
    assert "old" not in urls


def test_get_chat_model_prefer_orders_provider(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    monkeypatch.setenv("GROQ_API_KEY", "gr")
    from src.llm import _candidates

    cands = _candidates("small")
    labels = [c[1] for c in cands]
    assert any(lbl.startswith("google:") for lbl in labels)
    assert any(lbl.startswith("groq:") for lbl in labels)


def test_deterministic_supervisor_chooses_writer_at_cap():
    s = {
        "summaries": ["s"],
        "critique": "x",
        "sufficient": False,
        "iteration": 3,
        "max_iterations": 3,
    }
    assert _deterministic_supervisor(s) == "writer"


def test_supervisor_router_uses_deterministic_when_llm_off():
    from src.multi_agent import supervisor_router

    s = {"summaries": ["s"], "critique": "", "llm_supervisor": False}
    assert supervisor_router(s) == "critic"


def test_multi_agent_per_agent_models_smoke():
    """Verify per_agent_models doesn't break when llm is not None."""
    llm = make_fake_llm(
        [
            '{"sub_questions": ["q1"]}',
            "summary q1",
            "critique notes",
            '{"sufficient": true, "gaps": []}',
            "# Final\n\nDone.",
        ]
    )
    graph = build_multi_agent_graph(
        llm=llm,
        search_fn=lambda q: [{"url": "u", "content": "c", "score": 0.9, "published_date": _iso(10)}],
        per_agent_models=True,
    )
    out = graph.invoke(empty_state("X"))
    assert out["final_report"].startswith("# Final")
