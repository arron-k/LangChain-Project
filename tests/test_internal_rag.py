from src.internal_rag.connectors.base import BaseConnector, IngestDocument
from src.internal_rag.connectors.confluence import _html_to_text
from src.internal_rag.ingest import _chunk_documents


def test_ingest_document_dataclass():
    d = IngestDocument(
        doc_id="x:1",
        source="wiki",
        url="https://example.com/wiki/1",
        title="Hello",
        content="Body text",
    )
    assert d.metadata == {}
    assert d.source == "wiki"


def test_base_connector_requires_subclass():
    import pytest

    class Empty(BaseConnector):
        name = "empty"

    with pytest.raises(NotImplementedError):
        next(Empty().fetch_documents())


def test_html_to_text_strips_tags_and_collapses_whitespace():
    html = """
    <div><h1>Title</h1><script>alert('x')</script>
    <p>Hello   world</p><style>.x{}</style></div>
    """
    text = _html_to_text(html)
    assert "Title" in text and "Hello world" in text
    assert "alert" not in text


def test_html_to_text_handles_empty_input():
    assert _html_to_text("") == ""
    assert _html_to_text(None) == ""


def test_chunk_documents_splits_and_attaches_metadata():
    long_content = "Sentence. " * 400
    docs = [
        IngestDocument(
            doc_id="confluence:page:1",
            source="wiki",
            url="https://example.com/1",
            title="Doc A",
            content=long_content,
            metadata={"space_key": "ENG", "last_modified": "2025-01-01"},
        ),
    ]
    texts, metas, ids = _chunk_documents(docs, chunk_size=500, overlap=50)
    assert len(texts) > 1
    assert len(texts) == len(metas) == len(ids)
    assert metas[0]["source"] == "wiki"
    assert metas[0]["url"] == "https://example.com/1"
    assert metas[0]["space_key"] == "ENG"
    assert ids[0].startswith("confluence:page:1::chunk:")


def test_make_internal_search_fn_returns_searchfn_compatible(monkeypatch):
    """Even when Chroma isn't set up, the function should return a SearchFn that yields a list."""
    from src.internal_rag.retriever import make_internal_search_fn

    fn = make_internal_search_fn(sources=["wiki"], top_k=2)

    class FakeDoc:
        def __init__(self, content, meta):
            self.page_content = content
            self.metadata = meta

    class FakeStore:
        def similarity_search_with_score(self, query, k=2, filter=None):
            return [
                (
                    FakeDoc(
                        "Internal page about X",
                        {
                            "url": "https://wiki/ABC-1",
                            "title": "X notes",
                            "source": "wiki",
                            "last_modified": "2025-03-01",
                        },
                    ),
                    0.5,
                )
            ]

    import src.internal_rag.retriever as retriever_mod

    monkeypatch.setattr(
        retriever_mod, "make_internal_search_fn", make_internal_search_fn
    )

    import src.internal_rag.vector_store as vs

    monkeypatch.setattr(vs, "get_chroma", lambda persist_dir=None: FakeStore())

    hits = fn("anything")
    assert isinstance(hits, list)
    assert len(hits) == 1
    h = hits[0]
    for key in ("url", "content", "score", "title", "published_date", "source"):
        assert key in h
    assert h["source"] == "wiki"
    assert 0.0 <= h["score"] <= 1.0


def test_search_node_uses_internal_mode_when_state_says_so(monkeypatch):
    from src.nodes.search import search_node

    sentinel = [{"url": "u-int", "content": "internal hit", "score": 0.9, "title": "T", "published_date": "", "source": "wiki"}]

    import src.internal_rag.retriever as retriever_mod

    monkeypatch.setattr(retriever_mod, "make_internal_search_fn", lambda **kw: (lambda q: sentinel))

    out = search_node(
        {
            "sub_questions": ["q"],
            "search_mode": "internal",
            "internal_sources": ["wiki"],
        }
    )
    assert out["search_results"][0]["hits"] == sentinel


def test_search_node_defaults_to_web_when_no_mode(monkeypatch):
    from src.nodes.search import search_node

    web_calls = {"n": 0}

    def fake_web(q):
        web_calls["n"] += 1
        return [{"url": "u-web", "content": "web", "score": 0.5, "title": "", "published_date": ""}]

    out = search_node({"sub_questions": ["q"]}, search_fn=fake_web)
    assert web_calls["n"] == 1
    assert out["search_results"][0]["hits"][0]["url"] == "u-web"


def test_state_includes_search_mode_defaults():
    from src.state import empty_state

    s = empty_state("topic")
    assert s["search_mode"] == "web"
    assert s["internal_sources"] == ["wiki"]


def test_base_connector_signature_accepts_since_ts():
    from src.internal_rag.connectors.base import BaseConnector

    class Empty(BaseConnector):
        name = "empty"

    with __import__("pytest").raises(NotImplementedError):
        next(Empty().fetch_documents(since_ts=None))
    with __import__("pytest").raises(NotImplementedError):
        next(Empty().fetch_documents(since_ts=12345.6))


def test_slack_fetch_documents_accepts_since_ts():
    """Slack connector should accept since_ts param without crashing.

    We just verify signature/parameter handling — the actual fetch is patched.
    """
    import time

    from src.internal_rag.connectors.slack import SlackConnector

    class FakeClient:
        def users_list(self, cursor=None, limit=200):
            return {"members": [], "response_metadata": {}}

        def conversations_list(self, **kwargs):
            return {"channels": [], "response_metadata": {}}

    conn = SlackConnector(token="x", channel_names=[], lookback_days=1)
    conn._client = lambda: FakeClient()  # type: ignore[assignment]
    list(conn.fetch_documents(since_ts=time.time() - 100))
    list(conn.fetch_documents(since_ts=None))


def _patch_ingest_runtime(monkeypatch, tmp_path, captured: dict):
    from src.internal_rag import ingest as ingest_mod
    from src.internal_rag import sync_log as sync_log_mod

    log_path = tmp_path / "sync.sqlite"
    monkeypatch.setattr(sync_log_mod, "DEFAULT_PATH", str(log_path))

    class FakeConnector:
        def fetch_documents(self, since_ts=None):
            captured["since_ts"] = since_ts
            return iter([])

    monkeypatch.setattr(ingest_mod, "_get_connector", lambda name: FakeConnector())

    class FakeStore:
        class _collection:
            @staticmethod
            def delete(where=None):
                pass

        def add_texts(self, **kw):
            pass

    import src.internal_rag.vector_store as vs_mod

    monkeypatch.setattr(vs_mod, "get_chroma", lambda persist_dir=None: FakeStore())
    monkeypatch.setattr(vs_mod, "reset_collection", lambda persist_dir=None: None)
    return log_path


def test_ingest_incremental_uses_last_synced(monkeypatch, tmp_path):
    from src.internal_rag.ingest import ingest as run_ingest
    from src.internal_rag.sync_log import SyncLog

    captured: dict = {"since_ts": "NOT_SET"}
    log_path = _patch_ingest_runtime(monkeypatch, tmp_path, captured)

    SyncLog(log_path).record("wiki", docs=10, chunks=100, elapsed_sec=1.0)

    run_ingest(sources=["wiki"], incremental=True)
    assert captured["since_ts"] is not None
    assert captured["since_ts"] > 0


def test_ingest_full_mode_does_not_pass_since_ts(monkeypatch, tmp_path):
    from src.internal_rag.ingest import ingest as run_ingest
    from src.internal_rag.sync_log import SyncLog

    captured: dict = {"since_ts": "NOT_SET"}
    log_path = _patch_ingest_runtime(monkeypatch, tmp_path, captured)

    SyncLog(log_path).record("wiki", docs=10, chunks=100, elapsed_sec=1.0)

    run_ingest(sources=["wiki"], incremental=False)
    assert captured["since_ts"] is None


def test_confluence_filters_old_pages_when_since_ts(monkeypatch):
    """ConfluenceConnector should skip pages whose version.when < since_ts."""
    from datetime import datetime, timedelta, timezone

    from src.internal_rag.connectors.confluence import ConfluenceConnector

    now = datetime.now(timezone.utc)
    old_iso = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    fresh_iso = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    class FakeClient:
        def get_all_spaces(self, limit=100):
            return {"results": [{"key": "ENG"}]}

        def get_all_pages_from_space(self, space, start, limit, expand):
            if start > 0:
                return []
            return [
                {
                    "id": "1",
                    "title": "Old",
                    "body": {"storage": {"value": "<p>old content</p>"}},
                    "version": {"when": old_iso},
                },
                {
                    "id": "2",
                    "title": "Fresh",
                    "body": {"storage": {"value": "<p>fresh content</p>"}},
                    "version": {"when": fresh_iso},
                },
            ]

    conn = ConfluenceConnector(
        url="https://example.atlassian.net",
        username="u",
        api_token="t",
    )
    conn._client = lambda: FakeClient()  # type: ignore[assignment]

    since = (now - timedelta(days=5)).timestamp()
    docs = list(conn.fetch_documents(since_ts=since))
    assert len(docs) == 1
    assert docs[0].title == "Fresh"
