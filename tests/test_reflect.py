from src.nodes.reflect import reflect_node
from tests.conftest import make_fake_llm


def test_reflect_marks_sufficient_when_llm_says_so():
    llm = make_fake_llm(['{"sufficient": true, "gaps": []}'])
    out = reflect_node(
        {"topic": "X", "summaries": ["s1"], "iteration": 1}, llm=llm
    )
    assert out["sufficient"] is True
    assert out["sub_questions"] == []


def test_reflect_returns_gap_questions_when_insufficient():
    llm = make_fake_llm(
        ['{"sufficient": false, "gaps": ["follow-up A?", "follow-up B?"]}']
    )
    out = reflect_node(
        {"topic": "X", "summaries": ["s1"], "iteration": 1}, llm=llm
    )
    assert out["sufficient"] is False
    assert out["sub_questions"] == ["follow-up A?", "follow-up B?"]


def test_reflect_falls_back_to_sufficient_when_json_invalid():
    llm = make_fake_llm(["not json"])
    out = reflect_node(
        {"topic": "X", "summaries": ["s1"], "iteration": 1}, llm=llm
    )
    assert out["sufficient"] is True
