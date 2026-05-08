import sys
from functools import partial
from typing import Optional

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from src.nodes.critic import critic_node
from src.nodes.plan import plan_node
from src.nodes.reflect import reflect_node
from src.nodes.search import search_node
from src.nodes.summarize import summarize_node
from src.nodes.write import write_node
from src.state import ResearchState, empty_state
from src.tools.web_search import SearchFn

DEFAULT_MAX_ITERATIONS = 3


def _route_after_reflect(state: ResearchState) -> str:
    if state.get("sufficient", False):
        return "write"
    cap = int(state.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    if state.get("iteration", 0) >= cap:
        return "write"
    return "search"


def build_graph(
    llm: Optional[BaseChatModel] = None,
    llm_small: Optional[BaseChatModel] = None,
    llm_large: Optional[BaseChatModel] = None,
    search_fn: Optional[SearchFn] = None,
    checkpointer=None,
    interrupt_before: Optional[list[str]] = None,
    use_critic: bool = False,
    search_cache=None,
):
    small = llm_small or llm
    large = llm_large or llm

    builder = StateGraph(ResearchState)
    builder.add_node("plan", partial(plan_node, llm=small))
    builder.add_node(
        "search",
        partial(search_node, search_fn=search_fn, llm=small, cache=search_cache),
    )
    builder.add_node("summarize", partial(summarize_node, llm=large))
    if use_critic:
        builder.add_node("critic", partial(critic_node, llm=small))
    builder.add_node("reflect", partial(reflect_node, llm=small))
    builder.add_node("write", partial(write_node, llm=large))

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "search")
    builder.add_edge("search", "summarize")
    if use_critic:
        builder.add_edge("summarize", "critic")
        builder.add_edge("critic", "reflect")
    else:
        builder.add_edge("summarize", "reflect")
    builder.add_conditional_edges(
        "reflect", _route_after_reflect, {"search": "search", "write": "write"}
    )
    builder.add_edge("write", END)

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if interrupt_before:
        compile_kwargs["interrupt_before"] = interrupt_before
    return builder.compile(**compile_kwargs)


def _empty_state(topic: str, **overrides) -> ResearchState:
    return empty_state(topic, **overrides)


def _fake_llm():
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    return FakeListChatModel(
        responses=[
            '{"sub_questions": ["What is it?", "Why is it useful?", "How is it used?"]}',
            "Summary 1 [1].",
            "Summary 2 [1].",
            "Summary 3 [1].",
            '{"sufficient": true, "gaps": []}',
            "# Demo Report\n\nFake LLM output. Real Tavily sources below.",
        ]
    )


def main() -> None:
    load_dotenv()
    args = sys.argv[1:]
    use_fake = "--fake" in args
    args = [a for a in args if a != "--fake"]
    topic = args[0] if args else "LangGraph reflection patterns"

    graph = build_graph(llm=_fake_llm() if use_fake else None)
    out = graph.invoke(_empty_state(topic))
    print(out["final_report"])
    print(f"\n--- iterations: {out['iteration']}, sufficient: {out['sufficient']} ---")
    for entry in out["search_results"]:
        for h in entry["hits"]:
            print(h["url"])


if __name__ == "__main__":
    main()
