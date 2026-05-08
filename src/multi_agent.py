"""Multi-agent (Supervisor) orchestration.

Reuses the existing nodes (plan, search, summarize, critic, reflect, write)
but reorganizes them into role-bounded agents:
  - researcher_agent: plan + search + summarize  (one round)
  - critic_agent: critic + reflect              (review + verdict)
  - writer = the existing write_node
A central supervisor decides which agent runs next based on state.
"""

from functools import partial
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from src.nodes.critic import critic_node
from src.nodes.plan import plan_node
from src.nodes.reflect import reflect_node
from src.nodes.search import search_node
from src.nodes.summarize import summarize_node
from src.nodes.write import write_node
from src.state import ResearchState
from src.tools.web_search import SearchFn

RESEARCHER_PERSONA = (
    "You are a thorough Research Specialist. Cite many primary sources, include "
    "specific numbers/dates/names, prefer authoritative references, and avoid generalities."
)
CRITIC_PERSONA = (
    "You are a Strict Research Critic. Find vague claims, missing nuance, logical "
    "gaps, unsupported assertions, and inconsistencies. Be rigorous and unforgiving."
)
WRITER_PERSONA = (
    "You are an Editorial Writer. Prioritize clarity, narrative flow, well-structured "
    "sections, and turn raw facts into a coherent story for the reader."
)


def supervisor_router(state: ResearchState) -> str:
    """Decide which agent runs next."""
    if state.get("llm_supervisor"):
        decision = _llm_supervisor_decide(state)
        if decision in ("researcher", "critic", "writer", "END"):
            return decision
    return _deterministic_supervisor(state)


def _deterministic_supervisor(state: ResearchState) -> str:
    if state.get("final_report"):
        return "END"
    summaries = state.get("summaries") or []
    sub_questions = state.get("sub_questions") or []
    iter_count = int(state.get("iteration", 0) or 0)
    cap = int(state.get("max_iterations", 3) or 3)

    if not summaries:
        return "researcher"
    if not state.get("critique"):
        return "critic"
    if state.get("sufficient", False):
        return "writer"
    if iter_count >= cap:
        return "writer"
    if len(sub_questions) > 0:
        return "researcher"
    return "writer"


def _llm_supervisor_decide(state: ResearchState) -> str | None:
    if state.get("final_report"):
        return "END"
    iter_count = int(state.get("iteration", 0) or 0)
    cap = int(state.get("max_iterations", 3) or 3)
    if iter_count >= cap and state.get("summaries"):
        return "writer"

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.llm import get_structured_model
        from src.schemas import SupervisorDecision

        sup = get_structured_model("small", SupervisorDecision)
        sys = SystemMessage(
            content=(
                "You are a Supervisor coordinating three agents:\n"
                "- researcher: gathers info (plan + search + summarize)\n"
                "- critic: reviews summaries and decides if more research is needed\n"
                "- writer: composes the final report\n"
                "Choose what should run next based on the current state. "
                "Pick END only if the report is already done. "
                'Output JSON: {"next": "researcher|critic|writer|END", "reason": "..."}'
            )
        )
        summary_count = len(state.get("summaries") or [])
        critique = state.get("critique") or ""
        sufficient = state.get("sufficient", False)
        has_report = bool(state.get("final_report"))
        snapshot = (
            f"Topic: {state.get('topic', '')}\n"
            f"Sub-questions: {len(state.get('sub_questions') or [])}\n"
            f"Summaries gathered: {summary_count}\n"
            f"Iteration: {iter_count}/{cap}\n"
            f"Has critique: {bool(critique)}\n"
            f"Critique: {critique[:300]}\n"
            f"Sufficient flag: {sufficient}\n"
            f"Has final report: {has_report}"
        )
        user = HumanMessage(content=snapshot)
        out = sup.invoke([sys, user])
        if hasattr(out, "next") and out.next:
            return str(out.next).strip()
    except Exception:
        return None
    return None


def _researcher_agent(
    state: ResearchState,
    llm_small: Optional[BaseChatModel],
    llm_large: Optional[BaseChatModel],
    search_fn: Optional[SearchFn],
    search_cache,
) -> dict:
    state = {**state, "persona": RESEARCHER_PERSONA}
    plan_out = plan_node(state, llm=llm_small) if not state.get("sub_questions") or state.get("iteration", 0) > 0 else {}
    if plan_out:
        state = {**state, **plan_out}

    search_out = search_node(state, search_fn=search_fn, llm=llm_small, cache=search_cache)
    new_search_entries = search_out["search_results"]
    state_for_sum = {
        **state,
        "search_results": (state.get("search_results") or []) + new_search_entries,
        "iteration": search_out["iteration"],
    }

    summarize_out = summarize_node(state_for_sum, llm=llm_large)
    new_summaries = summarize_out["summaries"]

    return {
        **plan_out,
        "search_results": new_search_entries,
        "summaries": new_summaries,
        "iteration": search_out["iteration"],
        "critique": "",
        "sufficient": False,
    }


def _critic_agent(
    state: ResearchState,
    llm_small: Optional[BaseChatModel],
) -> dict:
    state = {**state, "persona": CRITIC_PERSONA}
    critic_out = critic_node(state, llm=llm_small)
    state_with_crit = {**state, **critic_out}
    reflect_out = reflect_node(state_with_crit, llm=llm_small)
    return {
        "critique": critic_out.get("critique", ""),
        "sufficient": reflect_out.get("sufficient", False),
        "sub_questions": reflect_out.get("sub_questions", []),
        "reflection": reflect_out.get("reflection", ""),
    }


def build_multi_agent_graph(
    llm: Optional[BaseChatModel] = None,
    llm_small: Optional[BaseChatModel] = None,
    llm_large: Optional[BaseChatModel] = None,
    search_fn: Optional[SearchFn] = None,
    checkpointer=None,
    interrupt_before: Optional[list[str]] = None,
    search_cache=None,
    per_agent_models: bool = False,
):
    small = llm_small or llm
    large = llm_large or llm

    researcher_llm = small
    critic_llm = small
    writer_llm = large

    if per_agent_models and llm is None and llm_small is None and llm_large is None:
        try:
            from src.llm import get_chat_model

            researcher_llm = get_chat_model("small", prefer="google")
            critic_llm = get_chat_model("large", prefer="groq")
            writer_llm = get_chat_model("large", prefer="google")
        except Exception:
            pass

    builder = StateGraph(ResearchState)

    def _supervisor(state):
        return {}

    builder.add_node("supervisor", _supervisor)
    builder.add_node(
        "researcher",
        partial(
            _researcher_agent,
            llm_small=researcher_llm,
            llm_large=writer_llm,
            search_fn=search_fn,
            search_cache=search_cache,
        ),
    )
    builder.add_node("critic", partial(_critic_agent, llm_small=critic_llm))

    def _writer_agent(state):
        return write_node({**state, "persona": WRITER_PERSONA}, llm=writer_llm)

    builder.add_node("writer", _writer_agent)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        supervisor_router,
        {
            "researcher": "researcher",
            "critic": "critic",
            "writer": "writer",
            "END": END,
        },
    )
    builder.add_edge("researcher", "supervisor")
    builder.add_edge("critic", "supervisor")
    builder.add_edge("writer", END)

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if interrupt_before:
        compile_kwargs["interrupt_before"] = interrupt_before
    return builder.compile(**compile_kwargs)
