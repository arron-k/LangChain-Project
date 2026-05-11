from src.nodes.write import write_node
from src.schemas import ClaimVerification, VerifiedClaim, WriterReview
from tests.conftest import make_fake_llm


def test_writer_review_schema():
    r = WriterReview(needs_revision=True, issues=["No sources"], suggestions="Add citations.")
    assert r.needs_revision is True
    assert "No sources" in r.issues


def test_writer_review_defaults():
    r = WriterReview(needs_revision=False)
    assert r.issues == []
    assert r.suggestions == ""


def test_claim_verification_schema():
    c = ClaimVerification(
        claims=[VerifiedClaim(text="X is fast", supported_by=[1, 2], risk="ok")],
        summary="Mostly verified",
    )
    assert c.claims[0].risk == "ok"
    assert c.summary == "Mostly verified"


def test_write_node_no_self_correct_skips_review():
    """When self_correct_writer is off, no extra LLM calls happen."""
    llm = make_fake_llm(["# Report\n\nBody [1]."])
    out = write_node(
        {
            "topic": "X",
            "summaries": ["s1"],
            "search_results": [{"question": "q1", "hits": [{"url": "https://a", "content": "c"}]}],
            "self_correct_writer": False,
        },
        llm=llm,
    )
    assert out["final_report"].startswith("# Report")


def test_write_node_self_correct_path_does_not_break_when_no_keys(monkeypatch):
    """Self-correct gracefully no-ops when get_structured_model fails."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    llm = make_fake_llm(["# Report\n\nBody [1]."])
    out = write_node(
        {
            "topic": "X",
            "summaries": ["s1"],
            "search_results": [{"question": "q1", "hits": [{"url": "https://a", "content": "c"}]}],
            "self_correct_writer": True,
        },
        llm=llm,
    )
    assert out["final_report"].startswith("# Report")


def test_write_node_cross_reference_safe_without_keys(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    llm = make_fake_llm(["# Report\n\nBody [1]."])
    out = write_node(
        {
            "topic": "X",
            "summaries": ["s1"],
            "search_results": [{"question": "q1", "hits": [{"url": "https://a", "content": "c"}]}],
            "cross_reference_check": True,
        },
        llm=llm,
    )
    assert out["final_report"].startswith("# Report")
    assert "claim_verification" not in out
