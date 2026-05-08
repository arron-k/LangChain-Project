from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def _system(language: str, persona: str = "") -> str:
    lang = "Critique in Korean." if language == "ko" else "Critique in English."
    base = (
        "You are a strict research critic. Read each summary and identify "
        "factual gaps, vague claims, missing nuance, or contradictions. "
        "Be terse — 2-3 bullet points per summary, max. "
        f"{lang}"
    )
    return f"{persona}\n\n{base}".strip() if persona else base


def critic_node(state: dict, llm: Optional[BaseChatModel] = None) -> dict:
    if llm is None:
        from src.llm import get_chat_model

        llm = get_chat_model("small")

    summaries = state.get("summaries", [])
    if not summaries:
        return {}

    payload = "\n\n---\n\n".join(
        f"Summary {i+1}:\n{s}" for i, s in enumerate(summaries)
    )
    msg = llm.invoke(
        [
            SystemMessage(content=_system(state.get("language", "en"), persona=state.get("persona", ""))),
            HumanMessage(content=payload),
        ]
    )
    from src.llm import to_text

    critique = to_text(getattr(msg, "content", msg))
    return {"critique": critique}
