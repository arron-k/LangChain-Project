from src.state import ResearchState


def test_research_state_keys():
    ann = ResearchState.__annotations__
    for key in (
        "topic",
        "sub_questions",
        "search_results",
        "summaries",
        "iteration",
        "sufficient",
        "reflection",
        "final_report",
    ):
        assert key in ann


def test_research_state_accepts_dict_literal():
    state: ResearchState = {
        "topic": "X",
        "sub_questions": [],
        "search_results": [],
        "summaries": [],
        "iteration": 0,
        "sufficient": False,
        "reflection": "",
        "final_report": "",
    }
    assert state["iteration"] == 0
