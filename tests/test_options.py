from src.graph import build_graph, _route_after_reflect
from src.nodes.plan import plan_node
from src.nodes.search import search_node
from src.nodes.write import write_node
from src.state import empty_state
from tests.conftest import make_fake_llm


def test_empty_state_has_default_options():
    s = empty_state("X")
    assert s["language"] == "en"
    assert s["num_questions"] == 3
    assert s["max_iterations"] == 3
    assert s["report_style"] == "concise"
    assert s["report_length"] == "medium"
    assert s["include_domains"] == []
    assert s["exclude_domains"] == []
    assert s["time_range"] == ""
    assert s["rerank"] is False


def test_empty_state_overrides():
    s = empty_state("X", language="ko", num_questions=5, max_iterations=1)
    assert s["language"] == "ko"
    assert s["num_questions"] == 5
    assert s["max_iterations"] == 1


def test_plan_node_respects_num_questions():
    llm = make_fake_llm(['{"sub_questions": ["q1", "q2", "q3", "q4", "q5"]}'])
    out = plan_node({"topic": "X", "num_questions": 2}, llm=llm)
    assert len(out["sub_questions"]) == 2


def test_router_uses_state_max_iterations():
    assert _route_after_reflect({"sufficient": False, "iteration": 1, "max_iterations": 1}) == "write"
    assert _route_after_reflect({"sufficient": False, "iteration": 0, "max_iterations": 3}) == "search"
    assert _route_after_reflect({"sufficient": True, "iteration": 0}) == "write"


def test_router_falls_back_to_default_when_max_missing():
    assert _route_after_reflect({"sufficient": False, "iteration": 5}) == "write"
    assert _route_after_reflect({"sufficient": False, "iteration": 2}) == "search"


def test_search_passes_filters_to_search_fn():
    captured = {}

    def fake_search(q):
        return [{"url": "u", "content": "c"}]

    out = search_node(
        {
            "sub_questions": ["q1"],
            "include_domains": ["github.com"],
            "exclude_domains": ["reddit.com"],
            "time_range": "week",
        },
        search_fn=fake_search,
    )
    assert out["search_results"][0]["question"] == "q1"


def test_search_rerank_reorders_hits_when_enabled():
    def fake_search(q):
        return [
            {"url": "u1", "content": "c1", "title": "t1"},
            {"url": "u2", "content": "c2", "title": "t2"},
            {"url": "u3", "content": "c3", "title": "t3"},
        ]

    rerank_llm = make_fake_llm(['{"scores": [1, 9, 5]}'])
    out = search_node(
        {"sub_questions": ["q1"], "rerank": True},
        search_fn=fake_search,
        llm=rerank_llm,
    )
    urls = [h["url"] for h in out["search_results"][0]["hits"]]
    assert urls == ["u2", "u3", "u1"]


def test_search_rerank_off_keeps_original_order():
    def fake_search(q):
        return [{"url": "u1", "content": "c1"}, {"url": "u2", "content": "c2"}]

    out = search_node(
        {"sub_questions": ["q1"], "rerank": False},
        search_fn=fake_search,
        llm=None,
    )
    urls = [h["url"] for h in out["search_results"][0]["hits"]]
    assert urls == ["u1", "u2"]


def test_write_node_accepts_style_and_length_options():
    llm = make_fake_llm(["# Report\n\nbody"])
    out = write_node(
        {
            "topic": "X",
            "language": "ko",
            "report_style": "academic",
            "report_length": "long",
            "summaries": ["s1"],
            "search_results": [{"question": "q1", "hits": [{"url": "u", "content": "c"}]}],
        },
        llm=llm,
    )
    assert out["final_report"].startswith("# Report")


def test_graph_runs_with_max_iterations_one():
    llm = make_fake_llm(
        [
            '{"sub_questions": ["q1"]}',
            "summary q1",
            '{"sufficient": false, "gaps": ["more"]}',
            "# Capped\n\ndone",
        ]
    )
    counter = {"calls": 0}

    def fake_search(q):
        counter["calls"] += 1
        return [{"url": "u", "content": "c"}]

    graph = build_graph(llm=llm, search_fn=fake_search)
    out = graph.invoke(empty_state("X", max_iterations=1))
    assert counter["calls"] == 1
    assert out["iteration"] == 1
    assert out["sufficient"] is False
    assert out["final_report"].startswith("# Capped")
