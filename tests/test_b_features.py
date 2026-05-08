import json
from pathlib import Path

from src.graph import build_graph
from src.lessons import load_lessons, save_lesson, relevant_lessons
from src.nodes.critic import critic_node
from src.nodes.plan import plan_node
from src.nodes.search import search_node
from src.state import empty_state
from tests.conftest import make_fake_llm


def _scripted():
    return [
        '{"sub_questions": ["q1"]}',
        "summary q1",
        "critique notes",
        '{"sufficient": true, "gaps": []}',
        "# Final\n\nDone.",
    ]


def _fake_search(q):
    return [{"url": f"u-{q}", "content": f"c-{q}", "score": 0.9}]


def test_critic_node_returns_critique_text():
    llm = make_fake_llm(["- gap A\n- gap B"])
    out = critic_node({"summaries": ["s1", "s2"], "language": "en"}, llm=llm)
    assert "gap" in out["critique"].lower()


def test_graph_with_critic_runs_full_path():
    llm = make_fake_llm(_scripted())
    graph = build_graph(llm=llm, search_fn=_fake_search, use_critic=True)
    out = graph.invoke(empty_state("X"))
    assert out["critique"] == "critique notes"
    assert out["final_report"].startswith("# Final")


def test_plan_node_uses_previous_reflection_on_revision():
    captured = {}

    class CapturingFake:
        def invoke(self, messages):
            captured["msgs"] = messages
            class M:
                content = '{"sub_questions": ["new q"]}'

            return M()

    plan_node(
        {
            "topic": "X",
            "iteration": 1,
            "reflection": "previous reflection text here",
            "num_questions": 1,
        },
        llm=CapturingFake(),
    )
    human = captured["msgs"][1].content
    assert "previous reflection text here" in human


def test_lessons_save_and_relevant(tmp_path: Path):
    lpath = tmp_path / "lessons.json"
    save_lesson("LangGraph reflection", "needed more depth", False, path=lpath)
    save_lesson("Vector DB", "good", True, path=lpath)
    save_lesson("LangGraph patterns", "clearer", True, path=lpath)

    items = load_lessons(lpath)
    assert len(items) == 3

    rel = relevant_lessons("LangGraph supervisor", path=lpath)
    assert len(rel) >= 1
    assert any("LangGraph" in r["topic"] for r in rel)


def test_search_filters_below_min_score_when_no_rerank():
    def fake_search(q):
        return [
            {"url": "u1", "content": "c1", "score": 0.9},
            {"url": "u2", "content": "c2", "score": 0.2},
            {"url": "u3", "content": "c3", "score": 0.5},
        ]

    out = search_node(
        {"sub_questions": ["q"], "min_hit_score": 0.4},
        search_fn=fake_search,
    )
    urls = [h["url"] for h in out["search_results"][0]["hits"]]
    assert "u2" not in urls


def test_search_extract_top_replaces_content():
    captured = {}

    def fake_search(q):
        return [{"url": "https://ex.com", "content": "short"}]

    import src.tools.web_search as ws

    original = ws.tavily_extract
    ws.tavily_extract = lambda url: "DEEP_CONTENT_FROM_EXTRACT"
    try:
        out = search_node(
            {"sub_questions": ["q"], "extract_top": True},
            search_fn=fake_search,
        )
        assert "DEEP_CONTENT" in out["search_results"][0]["hits"][0]["content"]
    finally:
        ws.tavily_extract = original
