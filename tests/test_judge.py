from pathlib import Path

from src.judge import JudgeStore
from src.schemas import JudgeScore


def _score(**overrides) -> JudgeScore:
    base = dict(
        accuracy=8.0,
        citations=7.0,
        structure=8.5,
        readability=9.0,
        length_fit=7.5,
        overall=8.0,
        comment="Solid report.",
    )
    base.update(overrides)
    return JudgeScore(**base)


def test_judge_score_clamps_range():
    s = _score()
    assert 0 <= s.overall <= 10
    assert s.comment


def test_judge_store_submit_and_latest(tmp_path: Path):
    js = JudgeStore(tmp_path / "j.sqlite")
    js.submit("T1", _score(overall=7.0), topic="X")
    js.submit("T1", _score(overall=8.5, comment="Better."), topic="X")
    latest = js.latest_for("T1")
    assert latest["overall"] == 8.5
    assert latest["comment"] == "Better."


def test_judge_store_stats_aggregates(tmp_path: Path):
    js = JudgeStore(tmp_path / "j.sqlite")
    js.submit("A", _score(overall=6, accuracy=6))
    js.submit("B", _score(overall=8, accuracy=8))
    js.submit("C", _score(overall=10, accuracy=10))
    s = js.stats()
    assert s["count"] == 3
    assert s["overall"] == 8.0
    assert s["accuracy"] == 8.0


def test_judge_store_returns_zero_when_empty(tmp_path: Path):
    js = JudgeStore(tmp_path / "j.sqlite")
    s = js.stats()
    assert s["count"] == 0


def test_judge_report_returns_none_for_empty():
    from src.judge import judge_report

    assert judge_report("topic", "", "en") is None
    assert judge_report("topic", "   \n", "en") is None
