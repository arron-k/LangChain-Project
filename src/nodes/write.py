import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def _link_inline_citations(text: str, urls: list[str]) -> str:
    if not urls:
        return text
    sources_marker = re.search(r"\n#+\s*Sources\s*\n", text, flags=re.IGNORECASE)
    if sources_marker:
        body, sources = text[: sources_marker.start()], text[sources_marker.start():]
    else:
        body, sources = text, ""

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if 1 <= n <= len(urls):
            return f"[\\[{n}\\]]({urls[n-1]})"
        return m.group(0)

    body = re.sub(r"(?<!\])\[(\d{1,2})\](?!\()", repl, body)
    return body + sources

STYLE_HINTS = {
    "concise": "Use a clear, direct, professional tone. No fluff.",
    "detailed": "Be thorough and explain trade-offs and nuances.",
    "academic": "Use formal academic tone with rigorous structure.",
    "blog": "Use an engaging conversational tone with relatable examples.",
}

LENGTH_HINTS = {
    "short": "Keep the report under 300 words.",
    "medium": "Aim for around 600-800 words.",
    "long": "Aim for 1200-1800 words with deeper analysis.",
}


def _system(language: str, style: str, length: str, persona: str = "") -> str:
    lang = "Write the entire report in Korean." if language == "ko" else "Write the entire report in English."
    style_hint = STYLE_HINTS.get(style, STYLE_HINTS["concise"])
    length_hint = LENGTH_HINTS.get(length, LENGTH_HINTS["medium"])
    base = (
        "You are a technical writer. Compose a markdown research report that "
        "starts with an H1 title, has clear sections per sub-question, and ends "
        "with a numbered Sources list as markdown links. "
        "Use [1], [2], ... inline citations that reference the Sources list. "
        f"{lang} {style_hint} {length_hint} "
        "Use only the provided summaries and URLs."
    )
    return f"{persona}\n\n{base}".strip() if persona else base


def write_node(state: dict, llm: Optional[BaseChatModel] = None) -> dict:
    if llm is None:
        from src.llm import get_chat_model

        llm = get_chat_model("large")

    topic = state.get("topic", "")
    language = state.get("language", "en")
    style = state.get("report_style", "concise")
    length = state.get("report_length", "medium")
    summaries = state.get("summaries", [])
    search_results = state.get("search_results", [])
    follow_up = state.get("follow_up", "") or ""

    sections = []
    for entry, summary in zip(search_results, summaries):
        sections.append(f"## {entry['question']}\n{summary}")

    urls = []
    for entry in search_results:
        for h in entry.get("hits", []):
            url = h.get("url", "")
            if url and url not in urls:
                urls.append(url)

    sources_md = "\n".join(f"{i+1}. [{u}]({u})" for i, u in enumerate(urls))
    follow_up_block = f"\n\nFollow-up focus: {follow_up}\n" if follow_up else ""
    payload = (
        f"Topic: {topic}{follow_up_block}\n\n"
        + "\n\n".join(sections)
        + "\n\nSources (use these as [1], [2], ...):\n"
        + sources_md
    )

    msg = llm.invoke(
        [
            SystemMessage(content=_system(language, style, length, persona=state.get("persona", ""))),
            HumanMessage(content=payload),
        ]
    )
    from src.llm import to_text

    text = to_text(getattr(msg, "content", msg))
    text = _link_inline_citations(text, urls)

    if state.get("use_lessons"):
        try:
            from src.lessons import save_lesson

            save_lesson(
                topic=state.get("topic", ""),
                reflection=state.get("reflection", ""),
                sufficient=state.get("sufficient", False),
            )
        except Exception:
            pass

    return {"final_report": text}
