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


def _counting_search(counter: dict):
    def _fn(q: str) -> list[dict]:
        counter["calls"] = counter.get("calls", 0) + 1
        return [{"url": f"u-{q}", "content": f"c-{q}"}]

    return _fn


def test_loop_runs_one_extra_iteration_then_terminates():
    llm = make_fake_llm(
        [
            '{"sub_questions": ["q1"]}',
            "summary q1 round1",
            '{"sufficient": false, "gaps": ["q1b"]}',
            "summary q1b round2",
            '{"sufficient": true, "gaps": []}',
            "# Final\n\nReport body.",
        ]
    )
    counter: dict = {}
    graph = build_graph(llm=llm, search_fn=_counting_search(counter))
    out = graph.invoke(_empty("X"))

    assert counter["calls"] == 2
    assert out["iteration"] == 2
    assert out["sufficient"] is True
    assert out["final_report"].startswith("# Final")


def test_loop_caps_at_max_iterations():
    insufficient = '{"sufficient": false, "gaps": ["more?"]}'
    llm = make_fake_llm(
        [
            '{"sub_questions": ["q1"]}',
            "s1",
            insufficient,
            "s2",
            insufficient,
            "s3",
            insufficient,
            "# Capped\n\nForced write after cap.",
        ]
    )
    counter: dict = {}
    graph = build_graph(llm=llm, search_fn=_counting_search(counter))
    out = graph.invoke(_empty("X"))

    assert counter["calls"] == 3
    assert out["iteration"] == 3
    assert out["sufficient"] is False
    assert out["final_report"].startswith("# Capped")
