from typing import Callable, Optional

SearchFn = Callable[[str], list[dict]]


def make_tavily_search(
    max_results: int = 3,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    time_range: str = "",
) -> SearchFn:
    from langchain_tavily import TavilySearch

    kwargs = {"max_results": max_results}
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
    if time_range:
        kwargs["time_range"] = time_range

    tool = TavilySearch(**kwargs)

    def _search(query: str) -> list[dict]:
        raw = tool.invoke({"query": query})
        items = raw.get("results", []) if isinstance(raw, dict) else raw
        return [
            {
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
                "title": r.get("title", ""),
                "published_date": r.get("published_date", ""),
            }
            for r in items
        ]

    return _search


def tavily_search(query: str, max_results: int = 3) -> list[dict]:
    return make_tavily_search(max_results=max_results)(query)


def tavily_extract(url: str) -> str:
    try:
        from langchain_tavily import TavilyExtract

        tool = TavilyExtract()
        raw = tool.invoke({"urls": [url]})
        if isinstance(raw, dict):
            results = raw.get("results", [])
            if results and isinstance(results, list):
                return results[0].get("raw_content", "") or results[0].get("content", "")
        return ""
    except Exception:
        return ""
