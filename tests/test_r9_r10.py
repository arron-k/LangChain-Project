from src.ab_compare import PRESETS, judge_pair
from src.schemas import ClaimVerification, JudgeScore, VerifiedClaim


def test_verified_claim_has_confidence_field():
    c = VerifiedClaim(text="X", supported_by=[1], risk="ok", confidence=8.5)
    assert c.confidence == 8.5


def test_verified_claim_confidence_default():
    c = VerifiedClaim(text="X")
    assert c.confidence == 5.0


def test_verified_claim_confidence_clamped():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VerifiedClaim(text="X", confidence=11.0)


def test_claim_verification_with_confidences():
    cv = ClaimVerification(
        claims=[
            VerifiedClaim(text="A", confidence=9.0, supported_by=[1, 2], risk="ok"),
            VerifiedClaim(text="B", confidence=4.0, supported_by=[3], risk="single-source"),
        ],
        summary="Mixed",
    )
    assert len(cv.claims) == 2
    avg = sum(c.confidence for c in cv.claims) / 2
    assert avg == 6.5


def test_presets_dict_has_expected_keys():
    assert "default" in PRESETS
    assert "max_quality" in PRESETS
    for k, v in PRESETS.items():
        assert "label" in v
        assert "options" in v
        assert isinstance(v["options"], dict)


def test_max_quality_preset_includes_advanced_features():
    opts = PRESETS["max_quality"]["options"]
    assert opts.get("multi_agent_mode") is True
    assert opts.get("self_correct_writer") is True
    assert opts.get("cross_reference_check") is True


def test_preset_label_returns_localized_string():
    from src.ab_compare import preset_label

    assert preset_label("default", "ko").startswith("🚀")
    assert "Basic" in preset_label("default", "en")
    assert "기본" in preset_label("default", "ko")


def test_preset_description_falls_back_to_english_for_unknown_lang():
    from src.ab_compare import preset_description

    en_desc = preset_description("max_quality", "en")
    fallback = preset_description("max_quality", "fr")
    assert en_desc == fallback


def test_preset_tags_present_for_all_presets():
    from src.ab_compare import preset_tags

    for k in PRESETS:
        assert preset_tags(k, "ko")
        assert preset_tags(k, "en")


def _score(overall: float) -> JudgeScore:
    return JudgeScore(
        accuracy=overall, citations=overall, structure=overall,
        readability=overall, length_fit=overall, overall=overall,
        comment="test",
    )


def test_judge_pair_picks_a_when_higher(monkeypatch):
    from src import ab_compare

    calls = iter([_score(8.5), _score(6.0)])
    monkeypatch.setattr(ab_compare, "judge_report", lambda *a, **kw: next(calls))

    result = judge_pair(
        "topic",
        {"final_report": "A report"},
        {"final_report": "B report"},
    )
    assert result["winner"] == "A"
    assert result["diff"] == 2.5


def test_judge_pair_returns_tie_when_close(monkeypatch):
    from src import ab_compare

    calls = iter([_score(7.0), _score(7.2)])
    monkeypatch.setattr(ab_compare, "judge_report", lambda *a, **kw: next(calls))

    result = judge_pair(
        "topic",
        {"final_report": "A"},
        {"final_report": "B"},
    )
    assert result["winner"] == "tie"


def test_judge_pair_handles_empty_reports():
    result = judge_pair("topic", {"final_report": ""}, {"final_report": ""})
    assert result["winner"] == "tie"
    assert result["score_a"] is None
    assert result["score_b"] is None
