from src.nodes.plan import plan_node
from src.nodes.search import search_node
from src.nodes.summarize import summarize_node
from src.nodes.write import write_node
from tests.conftest import make_fake_llm


def test_plan_node_extracts_sub_questions_from_json():
    llm = make_fake_llm(
        ['{"sub_questions": ["What is X?", "Why is X useful?", "How is X used?"]}']
    )
    out = plan_node({"topic": "X"}, llm=llm)
    assert out["sub_questions"] == [
        "What is X?",
        "Why is X useful?",
        "How is X used?",
    ]


def test_plan_node_falls_back_when_json_invalid():
    llm = make_fake_llm(["not json at all"])
    out = plan_node({"topic": "X"}, llm=llm)
    assert isinstance(out["sub_questions"], list)
    assert len(out["sub_questions"]) >= 1


def test_search_node_aggregates_results_per_question():
    def fake_search(q: str) -> list[dict]:
        return [{"url": f"https://ex.com/{q}", "content": f"content for {q}"}]

    state = {"sub_questions": ["q1", "q2"]}
    out = search_node(state, search_fn=fake_search)
    assert len(out["search_results"]) == 2
    assert out["search_results"][0]["question"] == "q1"
    assert out["search_results"][0]["hits"][0]["url"] == "https://ex.com/q1"


def test_summarize_node_produces_one_summary_per_question():
    llm = make_fake_llm(["summary-1", "summary-2"])
    state = {
        "search_results": [
            {"question": "q1", "hits": [{"url": "u1", "content": "c1"}]},
            {"question": "q2", "hits": [{"url": "u2", "content": "c2"}]},
        ]
    }
    out = summarize_node(state, llm=llm)
    assert out["summaries"] == ["summary-1", "summary-2"]


def test_write_node_produces_markdown_report():
    llm = make_fake_llm(["# Report\n\nFinal content."])
    state = {
        "topic": "LangGraph",
        "summaries": ["s1", "s2"],
        "search_results": [
            {"question": "q1", "hits": [{"url": "https://a", "content": "c"}]},
        ],
    }
    out = write_node(state, llm=llm)
    assert out["final_report"].startswith("# ")
    assert "Final content" in out["final_report"]
