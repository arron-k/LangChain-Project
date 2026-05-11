from src.internal_rag.hybrid import _merge, make_hybrid_search_fn


def _hit(url, content="c", score=0.5, title="", source=None):
    h = {"url": url, "content": content, "score": score, "title": title}
    if source:
        h["source"] = source
    return h


def test_hybrid_search_runs_both_and_merges():
    web_hits = [_hit("https://w/1", score=0.9), _hit("https://w/2", score=0.7)]
    int_hits = [_hit("https://i/1", score=0.8, source="wiki")]

    web_fn = lambda q: web_hits  # noqa: E731
    int_fn = lambda q: int_hits  # noqa: E731

    fn = make_hybrid_search_fn(web_fn, int_fn, web_weight=0.5, max_per_source=3)
    out = fn("anything")
    urls = [h["url"] for h in out]
    assert "https://w/1" in urls
    assert "https://i/1" in urls
    assert len(out) == 3


def test_hybrid_search_caps_per_source():
    web_hits = [_hit(f"https://w/{i}", score=1.0 - i * 0.1) for i in range(5)]
    int_hits = [_hit(f"https://i/{i}", score=1.0 - i * 0.1, source="wiki") for i in range(5)]

    fn = make_hybrid_search_fn(lambda q: web_hits, lambda q: int_hits, max_per_source=2)
    out = fn("q")
    web_count = sum(1 for h in out if h["source"] == "web")
    int_count = sum(1 for h in out if h["source"] == "wiki")
    assert web_count <= 2
    assert int_count <= 2


def test_hybrid_search_dedupes_by_url():
    web_hits = [_hit("https://shared", score=0.9)]
    int_hits = [_hit("https://shared", score=0.8, source="wiki")]

    fn = make_hybrid_search_fn(lambda q: web_hits, lambda q: int_hits)
    out = fn("q")
    assert len(out) == 1


def test_hybrid_search_assigns_default_source_for_web():
    fn = make_hybrid_search_fn(lambda q: [_hit("https://x")], lambda q: [])
    out = fn("q")
    assert out[0]["source"] == "web"


def test_hybrid_search_survives_one_side_failing():
    def bad(q):
        raise RuntimeError("nope")

    fn = make_hybrid_search_fn(bad, lambda q: [_hit("https://i/1", source="wiki")])
    out = fn("q")
    assert len(out) == 1
    assert out[0]["source"] == "wiki"


def test_hybrid_web_weight_zero_means_internal_only():
    web_hits = [_hit("https://w/1", score=0.99)]
    int_hits = [_hit("https://i/1", score=0.1, source="wiki")]

    fn = make_hybrid_search_fn(lambda q: web_hits, lambda q: int_hits, web_weight=0.0, max_per_source=1)
    out = fn("q")
    assert out[0]["url"] == "https://i/1"


def test_hybrid_web_weight_one_means_web_only():
    web_hits = [_hit("https://w/1", score=0.1)]
    int_hits = [_hit("https://i/1", score=0.99, source="wiki")]

    fn = make_hybrid_search_fn(lambda q: web_hits, lambda q: int_hits, web_weight=1.0, max_per_source=1)
    out = fn("q")
    assert out[0]["url"] == "https://w/1"


def test_state_includes_hybrid_defaults():
    from src.state import empty_state

    s = empty_state("topic")
    assert s["hybrid_web_weight"] == 0.5
    assert s["hybrid_max_per_source"] == 3


def test_search_node_handles_hybrid_mode(monkeypatch):
    from src.nodes import search as search_mod

    web_called = {"q": None}
    int_called = {"q": None}

    def fake_make_tavily(**kwargs):
        def _w(q):
            web_called["q"] = q
            return [{"url": "https://web/x", "content": "w", "score": 0.9, "title": ""}]

        return _w

    def fake_make_internal(**kwargs):
        def _i(q):
            int_called["q"] = q
            return [{"url": "https://wiki/y", "content": "i", "score": 0.7, "title": "", "source": "wiki"}]

        return _i

    monkeypatch.setattr(search_mod, "make_tavily_search", fake_make_tavily)
    import src.internal_rag.retriever as ret_mod

    monkeypatch.setattr(ret_mod, "make_internal_search_fn", fake_make_internal)

    out = search_mod.search_node(
        {
            "sub_questions": ["hybrid query"],
            "search_mode": "hybrid",
            "internal_sources": ["wiki"],
            "hybrid_web_weight": 0.5,
            "hybrid_max_per_source": 3,
        }
    )

    urls = [h["url"] for h in out["search_results"][0]["hits"]]
    assert "https://web/x" in urls
    assert "https://wiki/y" in urls
    assert web_called["q"] == "hybrid query"
    assert int_called["q"] == "hybrid query"
