from src.multi_agent import build_multi_agent_graph, supervisor_router
from src.nodes.search import _is_thin, search_node
from src.state import empty_state
from tests.conftest import make_fake_llm


def test_is_thin_detects_empty_results():
    assert _is_thin([]) is True


def test_is_thin_detects_single_result():
    assert _is_thin([{"url": "u", "content": "c", "score": 0.9}]) is True


def test_is_thin_detects_low_average_score():
    hits = [
        {"url": "u1", "content": "x" * 200, "score": 0.1},
        {"url": "u2", "content": "x" * 200, "score": 0.1},
    ]
    assert _is_thin(hits) is True


def test_is_thin_passes_strong_results():
    hits = [
        {"url": "u1", "content": "x" * 200, "score": 0.8},
        {"url": "u2", "content": "x" * 200, "score": 0.7},
    ]
    assert _is_thin(hits) is False


def test_self_rag_off_does_no_extra_call():
    counter = {"calls": 0}

    def fake(q):
        counter["calls"] += 1
        return [{"url": "u1", "content": "c", "score": 0.9}]

    state = {"sub_questions": ["q1"], "self_rag": False}
    out = search_node(state, search_fn=fake)
    assert counter["calls"] == 1
    assert out["search_results"][0]["question"] == "q1"


def test_supervisor_router_to_researcher_when_no_summaries():
    s = {"summaries": [], "sub_questions": []}
    assert supervisor_router(s) == "researcher"


def test_supervisor_router_to_critic_after_summaries():
    s = {"summaries": ["s1"], "critique": ""}
    assert supervisor_router(s) == "critic"


def test_supervisor_router_to_writer_when_sufficient():
    s = {"summaries": ["s1"], "critique": "ok", "sufficient": True}
    assert supervisor_router(s) == "writer"


def test_supervisor_router_to_researcher_again_when_insufficient_and_under_cap():
    s = {
        "summaries": ["s1"],
        "critique": "needs more",
        "sufficient": False,
        "iteration": 1,
        "max_iterations": 3,
        "sub_questions": ["q"],
    }
    assert supervisor_router(s) == "researcher"


def test_supervisor_router_to_writer_when_cap_reached():
    s = {
        "summaries": ["s1"],
        "critique": "needs more",
        "sufficient": False,
        "iteration": 3,
        "max_iterations": 3,
    }
    assert supervisor_router(s) == "writer"


def test_supervisor_router_returns_END_when_report_done():
    assert supervisor_router({"final_report": "# done"}) == "END"


def test_multi_agent_graph_runs_end_to_end_with_fakes():
    llm = make_fake_llm(
        [
            '{"sub_questions": ["q1"]}',
            "summary q1",
            "critique notes",
            '{"sufficient": true, "gaps": []}',
            "# Final\n\nDone.",
        ]
    )

    def fake_search(q):
        return [{"url": f"u-{q}", "content": f"c-{q}", "score": 0.9}]

    graph = build_multi_agent_graph(llm=llm, search_fn=fake_search)
    out = graph.invoke(empty_state("X"))
    assert out["final_report"].startswith("# Final")
    assert out["sufficient"] is True
