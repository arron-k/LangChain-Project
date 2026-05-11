import json
import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.tools.web_search import SearchFn, make_tavily_search

RERANK_SYSTEM = (
    "You score search hits by their relevance to the question on a 0-10 scale. "
    'Return ONLY JSON: {"scores": [n1, n2, ...]} matching the order of hits. '
    "No prose, no code fences."
)


def search_node(
    state: dict,
    search_fn: Optional[SearchFn] = None,
    llm: Optional[BaseChatModel] = None,
    cache=None,
) -> dict:
    cache_opts = {
        "include_domains": state.get("include_domains") or [],
        "exclude_domains": state.get("exclude_domains") or [],
        "time_range": state.get("time_range") or "",
        "max_results": 3,
    }

    if search_fn is None:
        mode = state.get("search_mode", "web")
        if mode == "internal":
            from src.internal_rag.retriever import make_internal_search_fn

            search_fn = make_internal_search_fn(
                sources=state.get("internal_sources") or ["wiki"],
                top_k=5,
            )
        elif mode == "hybrid":
            from src.internal_rag.hybrid import make_hybrid_search_fn
            from src.internal_rag.retriever import make_internal_search_fn

            web_fn = make_tavily_search(
                max_results=3,
                include_domains=cache_opts["include_domains"],
                exclude_domains=cache_opts["exclude_domains"],
                time_range=cache_opts["time_range"],
                include_images=bool(state.get("vision_enabled", False)),
            )
            int_fn = make_internal_search_fn(
                sources=state.get("internal_sources") or ["wiki"],
                top_k=5,
            )
            search_fn = make_hybrid_search_fn(
                web_fn=web_fn,
                internal_fn=int_fn,
                web_weight=float(state.get("hybrid_web_weight", 0.5)),
                max_per_source=int(state.get("hybrid_max_per_source", 3)),
            )
        else:
            search_fn = make_tavily_search(
                max_results=3,
                include_domains=cache_opts["include_domains"],
                exclude_domains=cache_opts["exclude_domains"],
                time_range=cache_opts["time_range"],
                include_images=bool(state.get("vision_enabled", False)),
            )

    if cache is not None and bool(state.get("use_cache", True)):
        from src.cache import with_cache

        search_fn = with_cache(search_fn, cache, cache_opts)

    rerank_enabled = bool(state.get("rerank", False))
    min_score = float(state.get("min_hit_score", 0.0))
    extract_top = bool(state.get("extract_top", False))
    self_rag = bool(state.get("self_rag", False))
    domain_dedup = bool(state.get("domain_dedup", False))
    max_per_domain = max(1, int(state.get("max_per_domain", 2) or 2))
    freshness_days = int(state.get("freshness_max_age_days", 0) or 0)

    results = []
    for q in state.get("sub_questions", []):
        hits = search_fn(q)
        if self_rag and _is_thin(hits):
            new_q = _reformulate(q, hits)
            if new_q and new_q != q:
                more = search_fn(new_q)
                hits = hits + more
        if rerank_enabled and llm is not None and len(hits) > 1:
            hits = _rerank_and_filter(llm, q, hits, min_score)
        elif min_score > 0:
            hits = [h for h in hits if float(h.get("score", 0)) >= min_score] or hits[:1]
        if domain_dedup and len(hits) > 1:
            hits = _diversify_by_domain(hits, max_per_domain=max_per_domain)
        if freshness_days > 0:
            hits = _filter_by_freshness(hits, freshness_days)
        if extract_top and hits:
            from src.tools.web_search import tavily_extract

            top = hits[0]
            deep = tavily_extract(top.get("url", ""))
            if deep:
                top["content"] = deep[:3000]
        results.append({"question": q, "hits": hits})
    return {
        "search_results": results,
        "iteration": state.get("iteration", 0) + 1,
    }


def _rerank_and_filter(
    llm: BaseChatModel, question: str, hits: list[dict], min_score: float = 0.0
) -> list[dict]:
    ranked = _rerank(llm, question, hits)
    if min_score > 0:
        scored = [(h, float(h.get("_rerank_score", 10.0))) for h in ranked]
        kept = [h for h, s in scored if s >= min_score]
        return kept or ranked[:1]
    return ranked


def _rerank(llm: BaseChatModel, question: str, hits: list[dict]) -> list[dict]:
    evidence = "\n\n".join(
        f"[{i}] {h.get('url', '')} | {h.get('title', '')}\n{h.get('content', '')[:300]}"
        for i, h in enumerate(hits)
    )
    try:
        msg = llm.invoke(
            [
                SystemMessage(content=RERANK_SYSTEM),
                HumanMessage(content=f"Question: {question}\n\nHits:\n{evidence}"),
            ]
        )
        from src.llm import to_text

        text = to_text(getattr(msg, "content", msg))
        scores = _parse_scores(text, n=len(hits))
        for h, s in zip(hits, scores):
            h["_rerank_score"] = s
        return [h for _, h in sorted(zip(scores, hits), key=lambda x: -x[0])]
    except Exception:
        return hits


def _filter_by_freshness(hits: list[dict], max_age_days: int) -> list[dict]:
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    kept = []
    for h in hits:
        d = (h.get("published_date") or "").strip()
        if not d:
            kept.append(h)
            continue
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                kept.append(h)
        except Exception:
            kept.append(h)
    return kept or hits[:1]


def _diversify_by_domain(hits: list[dict], max_per_domain: int = 2) -> list[dict]:
    from urllib.parse import urlparse

    counts: dict[str, int] = {}
    out: list[dict] = []
    for h in hits:
        try:
            netloc = urlparse(h.get("url", "")).netloc.lower()
        except Exception:
            netloc = ""
        if not netloc:
            out.append(h)
            continue
        if counts.get(netloc, 0) >= max_per_domain:
            continue
        counts[netloc] = counts.get(netloc, 0) + 1
        out.append(h)
    return out or hits[:1]


def _is_thin(hits: list[dict], min_count: int = 2, min_avg_score: float = 0.3) -> bool:
    if len(hits) < min_count:
        return True
    scores = [float(h.get("score", 0)) for h in hits]
    if scores and (sum(scores) / len(scores)) < min_avg_score:
        return True
    total_chars = sum(len((h.get("content") or "")) for h in hits)
    if total_chars < 200:
        return True
    return False


def _reformulate(query: str, hits: list[dict]) -> str | None:
    try:
        from src.llm import get_structured_model
        from src.schemas import QueryRewrite

        rewriter = get_structured_model("small", QueryRewrite)
        sys_msg = SystemMessage(
            content=(
                "Rewrite a web-search query that returned poor results. "
                "Make it more specific, add domain terms, drop ambiguous words. "
                "Output JSON only."
            )
        )
        sample = "\n".join(
            f"- {h.get('title') or ''}: {h.get('content','')[:120]}" for h in hits[:3]
        ) or "(no results)"
        user_msg = HumanMessage(
            content=f"Original query: {query}\n\nWeak results:\n{sample}\n\nGive a better query."
        )
        out = rewriter.invoke([sys_msg, user_msg])
        if hasattr(out, "query") and out.query:
            return str(out.query).strip()
    except Exception:
        return None
    return None


def _parse_scores(text: str, n: int) -> list[float]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            scores = data.get("scores", [])
            if isinstance(scores, list) and len(scores) >= n:
                return [float(s) for s in scores[:n]]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return [1.0] * n
