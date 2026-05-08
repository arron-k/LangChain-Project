from src.multi_agent import (
    CRITIC_PERSONA,
    RESEARCHER_PERSONA,
    WRITER_PERSONA,
    build_multi_agent_graph,
)
from src.nodes.search import _diversify_by_domain, search_node
from src.nodes.write import _link_inline_citations
from src.state import empty_state
from tests.conftest import make_fake_llm


def test_link_inline_citations_replaces_inline_brackets():
    text = "First claim [1]. Second claim [2]. Both true."
    out = _link_inline_citations(text, ["https://a.com", "https://b.com"])
    assert "[\\[1\\]](https://a.com)" in out
    assert "[\\[2\\]](https://b.com)" in out


def test_link_inline_citations_skips_already_linked():
    text = "Already [1](https://x.com) linked. Plain [2]."
    out = _link_inline_citations(text, ["https://a.com", "https://b.com"])
    assert "[1](https://x.com)" in out
    assert "[\\[2\\]](https://b.com)" in out


def test_link_inline_citations_does_not_touch_sources_section():
    text = "Body [1].\n\n# Sources\n1. [https://a.com](https://a.com)\n"
    out = _link_inline_citations(text, ["https://a.com"])
    assert "[\\[1\\]](https://a.com)" in out
    assert "# Sources" in out
    assert out.count("[https://a.com](https://a.com)") == 1


def test_link_inline_citations_handles_out_of_range():
    text = "Bad [99] reference."
    out = _link_inline_citations(text, ["https://a.com"])
    assert "[99]" in out


def test_diversify_by_domain_caps_repeats():
    hits = [
        {"url": "https://reddit.com/a"},
        {"url": "https://reddit.com/b"},
        {"url": "https://reddit.com/c"},
        {"url": "https://github.com/x"},
        {"url": "https://github.com/y"},
        {"url": "https://wikipedia.org/z"},
    ]
    out = _diversify_by_domain(hits, max_per_domain=2)
    assert len(out) == 5
    domains = [h["url"] for h in out]
    assert domains.count("https://reddit.com/c") == 0


def test_diversify_by_domain_max_one():
    hits = [
        {"url": "https://reddit.com/a"},
        {"url": "https://reddit.com/b"},
        {"url": "https://github.com/x"},
    ]
    out = _diversify_by_domain(hits, max_per_domain=1)
    assert len(out) == 2


def test_search_node_applies_domain_dedup_when_enabled():
    def fake(q):
        return [
            {"url": "https://reddit.com/a", "content": "x", "score": 0.9},
            {"url": "https://reddit.com/b", "content": "x", "score": 0.9},
            {"url": "https://reddit.com/c", "content": "x", "score": 0.9},
            {"url": "https://gh.com/x", "content": "x", "score": 0.9},
        ]

    out = search_node(
        {"sub_questions": ["q"], "domain_dedup": True, "max_per_domain": 1},
        search_fn=fake,
    )
    urls = [h["url"] for h in out["search_results"][0]["hits"]]
    reddit_count = sum(1 for u in urls if "reddit.com" in u)
    assert reddit_count == 1


def test_personas_constants_are_distinct():
    assert RESEARCHER_PERSONA != CRITIC_PERSONA
    assert CRITIC_PERSONA != WRITER_PERSONA
    assert "research" in RESEARCHER_PERSONA.lower()
    assert "critic" in CRITIC_PERSONA.lower()
    assert "writ" in WRITER_PERSONA.lower()


def test_persona_appears_in_plan_system_prompt():
    from src.nodes.plan import _system_prompt

    sys_with = _system_prompt("en", 3, persona="You are Researcher.")
    sys_without = _system_prompt("en", 3)
    assert "You are Researcher." in sys_with
    assert "You are Researcher." not in sys_without


def test_persona_appears_in_write_system_prompt():
    from src.nodes.write import _system

    s = _system("en", "concise", "medium", persona="You are Writer.")
    assert "You are Writer." in s


def test_multi_agent_graph_runs_with_personas():
    llm = make_fake_llm(
        [
            '{"sub_questions": ["q1"]}',
            "summary q1",
            "critique notes",
            '{"sufficient": true, "gaps": []}',
            "# Final\n\nDone.",
        ]
    )
    graph = build_multi_agent_graph(
        llm=llm,
        search_fn=lambda q: [{"url": "u", "content": "c", "score": 0.9}],
    )
    out = graph.invoke(empty_state("X"))
    assert out["final_report"].startswith("# Final")
