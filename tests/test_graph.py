from src.graph import build_graph
from src.state import ResearchState
from tests.conftest import make_fake_llm


def _empty(topic: str) -> ResearchState:
    return {
        "topic": topic,
        "sub_questions": [],
        "search_results": [],
        "summaries": [],
        "iteration": 0,
        "sufficient": False,
        "reflection": "",
        "final_report": "",
    }


def test_build_graph_returns_compiled_runnable():
    graph = build_graph(
        llm=make_fake_llm(["{}", "s", '{"sufficient": true}', "# r"]),
        search_fn=lambda q: [],
    )
    assert hasattr(graph, "invoke")


def test_graph_runs_end_to_end_when_first_pass_is_sufficient():
    llm = make_fake_llm(
        [
            '{"sub_questions": ["q1", "q2"]}',
            "summary of q1",
            "summary of q2",
            '{"sufficient": true, "gaps": []}',
            "# Final Report\n\nDone.",
        ]
    )

    def fake_search(q: str) -> list[dict]:
        return [{"url": f"u-{q}", "content": f"c-{q}"}]

    graph = build_graph(llm=llm, search_fn=fake_search)
    out = graph.invoke(_empty("LangGraph"))

    assert out["iteration"] == 1
    assert out["sufficient"] is True
    assert len(out["search_results"]) == 2
    assert out["summaries"] == ["summary of q1", "summary of q2"]
    assert out["final_report"].startswith("# Final Report")
