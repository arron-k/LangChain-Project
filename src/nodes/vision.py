"""Vision node — describes images attached to search hits via a multimodal LLM.

When state.vision_enabled is True, search_node attaches `_images` to the top hit
of each sub-question. This node iterates those images, calls a Vision LLM with
the question for context, and stores descriptions in state.image_findings.
"""

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def vision_node(state: dict, llm: Optional[BaseChatModel] = None) -> dict:
    if not state.get("vision_enabled"):
        return {}

    image_jobs: list[tuple[str, str, str]] = []
    new_search_results = state.get("search_results") or []
    for entry in new_search_results:
        question = entry.get("question", "")
        for hit in entry.get("hits", []):
            for img in (hit.get("_images") or [])[:2]:
                if img.get("url"):
                    image_jobs.append((question, img["url"], img.get("description", "")))

    if not image_jobs:
        return {}

    if llm is None:
        try:
            from src.llm import get_chat_model

            llm = get_chat_model("large")
        except Exception:
            return {}

    findings: list[dict] = []
    for question, url, hint in image_jobs[:5]:
        text = _describe_image(llm, url, question, hint, state.get("language", "en"))
        if text:
            findings.append({"url": url, "question": question, "description": text})

    if not findings:
        return {}
    return {"image_findings": findings}


def _describe_image(llm, url: str, question: str, hint: str, language: str) -> str | None:
    lang = "Respond in Korean." if language == "ko" else "Respond in English."
    sys = SystemMessage(
        content=(
            "You are a research assistant analyzing images from web sources. "
            "Describe what you see in 2-3 sentences and explain how it relates "
            f"to the question. Focus on charts, tables, diagrams, or numbers. {lang}"
        )
    )
    content = [
        {"type": "text", "text": f"Question: {question}\n\nHint: {hint}"},
        {"type": "image_url", "image_url": url},
    ]
    try:
        from src.llm import to_text

        msg = llm.invoke([sys, HumanMessage(content=content)])
        text = to_text(getattr(msg, "content", msg))
        return text.strip() if text else None
    except Exception:
        return None
