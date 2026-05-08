import time
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from src.cache import SearchCache, with_cache
from src.graph import build_graph
from src.persistence import delete_thread, list_thread_ids
from src.state import empty_state
from src.usage import UsageStore
from tests.conftest import make_fake_llm


def _scripted():
    return [
        '{"sub_questions": ["q1"]}',
        "summary q1",
        '{"sufficient": true, "gaps": []}',
        "# Final\n\nDone.",
    ]


def test_search_cache_returns_same_within_ttl(tmp_path: Path):
    cache = SearchCache(tmp_path / "c.sqlite", ttl_seconds=60)
    cache.set("q1", {"opt": 1}, [{"url": "u1"}])
    assert cache.get("q1", {"opt": 1}) == [{"url": "u1"}]


def test_search_cache_misses_when_opts_differ(tmp_path: Path):
    cache = SearchCache(tmp_path / "c.sqlite")
    cache.set("q1", {"opt": 1}, [{"url": "u1"}])
    assert cache.get("q1", {"opt": 2}) is None


def test_search_cache_expires(tmp_path: Path):
    cache = SearchCache(tmp_path / "c.sqlite", ttl_seconds=0.1)
    cache.set("q1", {}, [{"url": "u1"}])
    time.sleep(0.2)
    assert cache.get("q1", {}) is None


def test_with_cache_avoids_second_call(tmp_path: Path):
    cache = SearchCache(tmp_path / "c.sqlite")
    calls = {"n": 0}

    def search(q):
        calls["n"] += 1
        return [{"url": q}]

    cached = with_cache(search, cache, {})
    cached("q1")
    cached("q1")
    cached("q1")
    assert calls["n"] == 1


def test_search_cache_stats(tmp_path: Path):
    cache = SearchCache(tmp_path / "c.sqlite")
    cache.set("a", {}, [])
    cache.set("b", {}, [])
    s = cache.stats()
    assert s["count"] == 2
    assert s["live"] == 2


def test_usage_store_logs_and_aggregates(tmp_path: Path):
    store = UsageStore(tmp_path / "u.sqlite")
    store.log("google", "gemini-flash", "small", 0.5, ok=True)
    store.log("google", "gemini-flash", "small", 0.7, ok=True)
    store.log("anthropic", "claude", "large", 1.2, ok=False)
    s = store.stats(since_seconds=3600)
    assert s["total_calls"] == 3
    assert s["successful_calls"] == 2
    by_model = {(c["provider"], c["model"]): c for c in s["by_combo"]}
    assert by_model[("google", "gemini-flash")]["count"] == 2


def test_delete_thread_removes_from_saver():
    saver = MemorySaver()
    graph = build_graph(
        llm=make_fake_llm(_scripted()),
        search_fn=lambda q: [{"url": "u", "content": "c"}],
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "T-DEL"}}
    graph.invoke(empty_state("X"), config=config)

    assert "T-DEL" in list_thread_ids(saver)
    ok = delete_thread(saver, "T-DEL")
    assert ok or "T-DEL" not in list_thread_ids(saver)


def test_secrets_status_masks_keys(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyTESTKEY1234567890")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from src.llm import secrets_status

    s = secrets_status()
    assert s["GOOGLE_API_KEY"]["set"] is True
    assert s["GOOGLE_API_KEY"]["masked"].startswith("AIza")
    assert "*" in s["GOOGLE_API_KEY"]["masked"]
    assert s["ANTHROPIC_API_KEY"]["set"] is False
