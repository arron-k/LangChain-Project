from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph
from src.state import ResearchState
from tests.conftest import make_fake_llm


def _empty(topic: str) -> ResearchState:
    return {
        "topic": topic,
        "sub_questions": [],
        "search_results": [],
        "summaries": [],
        "iteration": 0,
        "sufficient": False,
        "reflection": "",
        "final_report": "",
    }


def _scripted_responses() -> list[str]:
    return [
        '{"sub_questions": ["q1"]}',
        "summary q1",
        '{"sufficient": true, "gaps": []}',
        "# Final\n\nDone.",
    ]


def _fake_search(q: str) -> list[dict]:
    return [{"url": f"u-{q}", "content": f"c-{q}"}]


def test_checkpointer_persists_final_state():
    saver = MemorySaver()
    graph = build_graph(
        llm=make_fake_llm(_scripted_responses()),
        search_fn=_fake_search,
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "t1"}}
    out = graph.invoke(_empty("X"), config=config)

    snap = graph.get_state(config)
    assert snap.values["final_report"] == out["final_report"]
    assert snap.values["iteration"] == 1


def test_threads_are_isolated():
    saver = MemorySaver()

    def make_graph():
        return build_graph(
            llm=make_fake_llm(_scripted_responses()),
            search_fn=_fake_search,
            checkpointer=saver,
        )

    make_graph().invoke(_empty("alpha"), config={"configurable": {"thread_id": "A"}})
    make_graph().invoke(_empty("beta"), config={"configurable": {"thread_id": "B"}})

    snap_a = make_graph().get_state({"configurable": {"thread_id": "A"}})
    snap_b = make_graph().get_state({"configurable": {"thread_id": "B"}})
    assert snap_a.values["topic"] == "alpha"
    assert snap_b.values["topic"] == "beta"


def test_interrupt_before_write_then_resume():
    saver = MemorySaver()
    graph = build_graph(
        llm=make_fake_llm(_scripted_responses()),
        search_fn=_fake_search,
        checkpointer=saver,
        interrupt_before=["write"],
    )
    config = {"configurable": {"thread_id": "t-int"}}

    out1 = graph.invoke(_empty("X"), config=config)
    assert out1["final_report"] == ""
    assert out1["iteration"] == 1
    assert out1["sufficient"] is True

    out2 = graph.invoke(None, config=config)
    assert out2["final_report"].startswith("# Final")


def test_list_thread_ids_returns_used_threads():
    from src.persistence import list_thread_ids

    saver = MemorySaver()
    g1 = build_graph(
        llm=make_fake_llm(_scripted_responses()),
        search_fn=_fake_search,
        checkpointer=saver,
    )
    g1.invoke(_empty("alpha"), config={"configurable": {"thread_id": "T-A"}})

    g2 = build_graph(
        llm=make_fake_llm(_scripted_responses()),
        search_fn=_fake_search,
        checkpointer=saver,
    )
    g2.invoke(_empty("beta"), config={"configurable": {"thread_id": "T-B"}})

    ids = list_thread_ids(saver)
    assert set(ids) == {"T-A", "T-B"}


def test_thread_summaries_includes_topic_and_status():
    from src.persistence import thread_summaries

    saver = MemorySaver()
    graph = build_graph(
        llm=make_fake_llm(_scripted_responses()),
        search_fn=_fake_search,
        checkpointer=saver,
    )
    graph.invoke(_empty("topic-A"), config={"configurable": {"thread_id": "T-1"}})

    summaries = thread_summaries(graph, saver)
    by_id = {s["thread_id"]: s for s in summaries}
    assert by_id["T-1"]["topic"] == "topic-A"
    assert by_id["T-1"]["has_report"] is True
    assert by_id["T-1"]["iteration"] >= 1


def test_stream_emits_one_event_per_node():
    graph = build_graph(
        llm=make_fake_llm(_scripted_responses()),
        search_fn=_fake_search,
    )
    nodes_seen = []
    for chunk in graph.stream(_empty("X"), stream_mode="updates"):
        nodes_seen.extend(chunk.keys())

    assert nodes_seen == ["plan", "search", "summarize", "reflect", "write"]
