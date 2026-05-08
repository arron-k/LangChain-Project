from pathlib import Path

from src.exporters import markdown_to_docx_bytes, markdown_to_pdf_bytes
from src.i18n import t
from src.thread_meta import ThreadMeta


def test_thread_meta_get_returns_defaults_when_missing(tmp_path: Path):
    m = ThreadMeta(tmp_path / "tm.sqlite")
    out = m.get("nope")
    assert out["display_name"] == ""
    assert out["tags"] == []
    assert out["favorite"] is False


def test_thread_meta_upsert_and_read(tmp_path: Path):
    m = ThreadMeta(tmp_path / "tm.sqlite")
    m.upsert("T1", display_name="LangGraph 학습", tags=["langgraph", "study"], favorite=True)
    out = m.get("T1")
    assert out["display_name"] == "LangGraph 학습"
    assert out["tags"] == ["langgraph", "study"]
    assert out["favorite"] is True


def test_thread_meta_toggle_favorite(tmp_path: Path):
    m = ThreadMeta(tmp_path / "tm.sqlite")
    assert m.toggle_favorite("X") is True
    assert m.get("X")["favorite"] is True
    assert m.toggle_favorite("X") is False


def test_thread_meta_all(tmp_path: Path):
    m = ThreadMeta(tmp_path / "tm.sqlite")
    m.upsert("a", favorite=True)
    m.upsert("b", display_name="b-name")
    all_meta = m.all()
    assert "a" in all_meta and "b" in all_meta
    assert all_meta["a"]["favorite"] is True


def test_markdown_to_pdf_returns_pdf_bytes():
    md = "# Title\n\nHello world.\n\n## Section\n\n- item one\n- item two\n"
    data = markdown_to_pdf_bytes(md)
    assert isinstance(data, bytes) and len(data) > 100
    assert data[:4] == b"%PDF"


def test_markdown_to_docx_returns_docx_bytes():
    md = "# Report\n\n## Q1\nAnswer paragraph.\n\n- bullet a\n- bullet b\n"
    data = markdown_to_docx_bytes(md)
    assert isinstance(data, bytes) and len(data) > 100
    assert data[:2] == b"PK"


def test_i18n_translates_known_keys():
    assert t("run", "en") == "🚀 Run"
    assert t("run", "ko") == "🚀 실행"
    assert t("nonexistent", "en") == "nonexistent"
