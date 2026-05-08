from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def _system(language: str, persona: str = "") -> str:
    lang_line = "Write the summary in Korean." if language == "ko" else "Write the summary in English."
    base = (
        "You are a careful research assistant. "
        "Given a question and search hits, write a concise (3-5 sentence) summary "
        f"that directly answers the question. {lang_line} "
        "Cite source URLs inline as [1], [2]."
    )
    return f"{persona}\n\n{base}".strip() if persona else base


def summarize_node(state: dict, llm: Optional[BaseChatModel] = None) -> dict:
    if llm is None:
        from src.llm import get_chat_model

        llm = get_chat_model("large")

    language = state.get("language", "en")
    already = len(state.get("summaries", []))
    pending = state.get("search_results", [])[already:]
    summaries: list[str] = []
    for entry in pending:
        question = entry["question"]
        hits = entry.get("hits", [])
        evidence = "\n\n".join(
            f"[{i+1}] {h.get('url', '')}\n{h.get('content', '')}"
            for i, h in enumerate(hits)
        )
        msg = llm.invoke(
            [
                SystemMessage(content=_system(language, persona=state.get("persona", ""))),
                HumanMessage(content=f"Question: {question}\n\nEvidence:\n{evidence}"),
            ]
        )
        from src.llm import to_text

        text = to_text(getattr(msg, "content", msg))
        summaries.append(text)
    return {"summaries": summaries}
