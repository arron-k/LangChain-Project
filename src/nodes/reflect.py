import json
import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

def _system(language: str, persona: str = "") -> str:
    lang_line = (
        "If you produce gap questions, write them in Korean."
        if language == "ko"
        else "If you produce gap questions, write them in English."
    )
    base = (
        "You are a pragmatic research critic. Given the topic and current summaries, "
        "decide whether they form a REASONABLE answer for a short research report. "
        "Be lenient: if the summaries cover the main aspects, mark sufficient=true. "
        "Only request more searches if there is a clear, important gap. "
        f"{lang_line} "
        'Return ONLY JSON: {"sufficient": bool, "gaps": ["follow-up question", ...]}. '
        "Limit gaps to at most 2 items. No prose, no code fences."
    )
    return f"{persona}\n\n{base}".strip() if persona else base


def reflect_node(state: dict, llm: Optional[BaseChatModel] = None) -> dict:
    topic = state.get("topic", "")
    summaries = state.get("summaries", [])
    critique = state.get("critique", "")
    parts = [f"Topic: {topic}", "Summaries so far:\n" + "\n---\n".join(summaries)]
    if critique:
        parts.append("Critic notes:\n" + critique)
    payload = "\n\n".join(parts)

    language = state.get("language", "en")
    messages = [
        SystemMessage(content=_system(language, persona=state.get("persona", ""))),
        HumanMessage(content=payload),
    ]

    if llm is None:
        try:
            from src.llm import get_structured_model
            from src.schemas import ReflectOutput

            structured = get_structured_model("small", ReflectOutput)
            result = structured.invoke(messages)
            if hasattr(result, "sufficient"):
                return {
                    "sufficient": bool(result.sufficient),
                    "sub_questions": list(result.gaps or [])[:2],
                    "reflection": (
                        f"sufficient={result.sufficient} gaps={list(result.gaps or [])}"
                    ),
                }
        except Exception:
            pass
        from src.llm import get_chat_model

        llm = get_chat_model("small")

    msg = llm.invoke(messages)
    from src.llm import to_text

    text = to_text(getattr(msg, "content", msg))
    sufficient, gaps = _parse(text)
    return {
        "sufficient": sufficient,
        "sub_questions": gaps,
        "reflection": text,
    }


def _parse(text: str) -> tuple[bool, list[str]]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return True, []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return True, []
    sufficient = bool(data.get("sufficient", True))
    gaps_raw = data.get("gaps", [])
    gaps = [str(g) for g in gaps_raw] if isinstance(gaps_raw, list) else []
    return sufficient, gaps
