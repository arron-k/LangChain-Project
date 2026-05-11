"""Hybrid retriever: run web + internal in parallel, merge results."""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

SearchFn = Callable[[str], list[dict]]


def _normalize_scores(hits: list[dict]) -> list[dict]:
    """Min-max normalize hit scores within a single result list."""
    if not hits:
        return hits
    scores = [float(h.get("score", 0.0)) for h in hits]
    lo, hi = min(scores), max(scores)
    span = hi - lo
    for h in hits:
        raw = float(h.get("score", 0.0))
        h["_norm_score"] = (raw - lo) / span if span > 0 else 1.0
    return hits


def _merge(
    web_hits: list[dict],
    internal_hits: list[dict],
    web_weight: float = 0.5,
    max_per_source: int = 3,
) -> list[dict]:
    """Merge two hit lists with score normalization + per-source quota + URL dedup."""
    for h in web_hits:
        h.setdefault("source", "web")
    for h in internal_hits:
        h.setdefault("source", h.get("source", "internal") or "internal")

    web_hits = _normalize_scores(list(web_hits))
    internal_hits = _normalize_scores(list(internal_hits))

    for h in web_hits:
        h["_combined_score"] = h.get("_norm_score", 0.0) * web_weight
    for h in internal_hits:
        h["_combined_score"] = h.get("_norm_score", 0.0) * (1.0 - web_weight)

    web_top = sorted(web_hits, key=lambda x: -x.get("_combined_score", 0.0))[:max_per_source]
    int_top = sorted(internal_hits, key=lambda x: -x.get("_combined_score", 0.0))[:max_per_source]

    seen: set[str] = set()
    merged: list[dict] = []
    for h in sorted(web_top + int_top, key=lambda x: -x.get("_combined_score", 0.0)):
        url = h.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        merged.append(h)
    return merged


def make_hybrid_search_fn(
    web_fn: SearchFn,
    internal_fn: SearchFn,
    web_weight: float = 0.5,
    max_per_source: int = 3,
) -> SearchFn:
    """Return a SearchFn that runs both fn's in parallel and merges results."""

    def _search(query: str) -> list[dict]:
        with ThreadPoolExecutor(max_workers=2) as ex:
            web_future = ex.submit(_safe_call, web_fn, query)
            int_future = ex.submit(_safe_call, internal_fn, query)
            web_hits = web_future.result()
            int_hits = int_future.result()
        return _merge(web_hits, int_hits, web_weight=web_weight, max_per_source=max_per_source)

    return _search


def _safe_call(fn: Optional[SearchFn], query: str) -> list[dict]:
    if fn is None:
        return []
    try:
        return fn(query) or []
    except Exception:
        return []
