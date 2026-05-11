from typing import Optional


def make_internal_search_fn(
    sources: Optional[list[str]] = None,
    top_k: int = 5,
    persist_dir: Optional[str] = None,
):
    """Return a SearchFn-compatible callable that queries the internal Chroma store."""

    sources = sources or ["wiki"]

    def _search(query: str) -> list[dict]:
        from src.internal_rag.vector_store import get_chroma

        store = get_chroma(persist_dir=persist_dir)
        filt = {"source": {"$in": sources}} if sources else None
        try:
            results = store.similarity_search_with_score(query, k=top_k, filter=filt)
        except Exception:
            results = []
        hits = []
        for doc, score in results:
            meta = doc.metadata or {}
            normalized_score = max(0.0, min(1.0, 1.0 - float(score) / 2.0))
            hits.append(
                {
                    "url": meta.get("url", ""),
                    "content": doc.page_content,
                    "score": normalized_score,
                    "title": meta.get("title", ""),
                    "published_date": meta.get("last_modified", ""),
                    "source": meta.get("source", "wiki"),
                }
            )
        return hits

    return _search
