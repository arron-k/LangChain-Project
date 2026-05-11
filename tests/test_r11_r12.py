from pathlib import Path

from src.lessons import load_lessons, relevant_reflexions, save_reflexion
from src.nodes.vision import vision_node
from src.schemas import ReflexionMemo
from src.state import empty_state


def test_reflexion_memo_schema():
    m = ReflexionMemo(
        topic="X",
        what_worked=["A", "B"],
        what_to_improve=["C"],
        strategy_for_next_time="Do D.",
    )
    assert m.topic == "X"
    assert m.what_worked == ["A", "B"]
    assert m.strategy_for_next_time == "Do D."


def test_reflexion_memo_defaults():
    m = ReflexionMemo(topic="Y")
    assert m.what_worked == []
    assert m.what_to_improve == []
    assert m.strategy_for_next_time == ""


def test_save_and_load_structured_reflexion(tmp_path: Path):
    p = tmp_path / "lessons.json"
    save_reflexion(
        {"topic": "LangGraph", "what_worked": ["x"], "what_to_improve": ["y"], "strategy_for_next_time": "z"},
        path=p,
    )
    items = load_lessons(p)
    assert len(items) == 1
    assert items[0]["structured"]["topic"] == "LangGraph"


def test_relevant_reflexions_returns_overlapping(tmp_path: Path):
    p = tmp_path / "lessons.json"
    save_reflexion({"topic": "LangGraph reflection", "what_to_improve": ["depth"]}, path=p)
    save_reflexion({"topic": "Vector DB"}, path=p)
    save_reflexion({"topic": "LangGraph patterns"}, path=p)

    rel = relevant_reflexions("LangGraph supervisor", path=p)
    assert len(rel) >= 1
    assert any("LangGraph" in r["topic"] for r in rel)


def test_relevant_reflexions_returns_empty_when_no_overlap(tmp_path: Path):
    p = tmp_path / "lessons.json"
    save_reflexion({"topic": "topic A"}, path=p)
    rel = relevant_reflexions("totally unrelated", path=p)
    assert rel == []


def test_vision_node_no_op_when_disabled():
    out = vision_node({"vision_enabled": False, "search_results": []})
    assert out == {}


def test_vision_node_no_op_when_no_images():
    state = {
        "vision_enabled": True,
        "search_results": [
            {"question": "q1", "hits": [{"url": "u", "content": "c"}]},
        ],
    }
    out = vision_node(state)
    assert out == {}


def test_vision_node_handles_llm_unavailable(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    state = {
        "vision_enabled": True,
        "search_results": [
            {
                "question": "q1",
                "hits": [
                    {
                        "url": "u",
                        "content": "c",
                        "_images": [{"url": "https://example.com/img.png"}],
                    }
                ],
            }
        ],
    }
    out = vision_node(state)
    assert out == {}


def test_empty_state_includes_vision_and_reflexion_defaults():
    s = empty_state("X")
    assert s["vision_enabled"] is False
    assert s["reflexion_enabled"] is False
