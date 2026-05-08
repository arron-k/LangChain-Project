import os

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.mark.skipif(
    not os.getenv("TAVILY_API_KEY"),
    reason="TAVILY_API_KEY not set",
)
def test_tavily_search_returns_hits():
    from src.tools.web_search import tavily_search

    hits = tavily_search("What is LangGraph?", max_results=2)
    assert isinstance(hits, list)
    assert len(hits) >= 1
    assert "url" in hits[0]
    assert "content" in hits[0]
