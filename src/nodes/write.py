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

    image_findings = state.get("image_findings") or []
    images_block = ""
    if image_findings:
        images_block = "\n\nVisual findings (from images on source pages):\n" + "\n".join(
            f"- ({f.get('question','')}) {f.get('description','')[:300]}"
            for f in image_findings
        )

    payload = (
        f"Topic: {topic}{follow_up_block}\n\n"
        + "\n\n".join(sections)
        + images_block
        + "\n\nSources (use these as [1], [2], ...):\n"
        + sources_md
    )

    base_messages = [
        SystemMessage(content=_system(language, style, length, persona=state.get("persona", ""))),
        HumanMessage(content=payload),
    ]
    msg = llm.invoke(base_messages)
    from src.llm import to_text

    text = to_text(getattr(msg, "content", msg))

    if state.get("self_correct_writer"):
        revised = _maybe_revise(text, state, payload, base_messages, llm)
        if revised:
            text = revised

    text = _link_inline_citations(text, urls)

    extras: dict = {}
    if state.get("cross_reference_check") and urls:
        verification = _verify_claims(text, urls, language)
        if verification is not None:
            extras["claim_verification"] = verification

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

    if state.get("reflexion_enabled"):
        memo = _generate_reflexion(state, text)
        if memo is not None:
            extras["reflexion_memo"] = memo
            try:
                from src.lessons import save_reflexion

                save_reflexion(memo)
            except Exception:
                pass

    return {"final_report": text, **extras}


def _generate_reflexion(state: dict, report: str) -> dict | None:
    try:
        from src.llm import get_structured_model
        from src.schemas import ReflexionMemo

        reflector = get_structured_model("small", ReflexionMemo)
        lang = (
            "Use Korean for the memo."
            if state.get("language") == "ko"
            else "Use English for the memo."
        )
        sys = SystemMessage(
            content=(
                "You are reflecting on a research run that just ended. "
                "Generate a concise self-reflection memo describing what worked, "
                "what could be improved, and a single concrete strategy for next time. "
                "Focus on actionable lessons (not generic advice). "
                f"{lang}"
            )
        )
        snapshot = (
            f"Topic: {state.get('topic', '')}\n"
            f"Iterations: {state.get('iteration', 0)} / cap {state.get('max_iterations', 3)}\n"
            f"Sufficient flag: {state.get('sufficient', False)}\n"
            f"Sub-questions count: {len(state.get('sub_questions') or [])}\n"
            f"Summaries count: {len(state.get('summaries') or [])}\n"
            f"Critique: {state.get('critique', '')[:300]}\n"
            f"Reflection: {state.get('reflection', '')[:300]}\n"
            f"\n--- Final report (first 1500 chars) ---\n{report[:1500]}"
        )
        result = reflector.invoke([sys, HumanMessage(content=snapshot)])
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
    except Exception:
        return None
    return None


def _maybe_revise(text: str, state: dict, payload: str, base_messages, llm) -> str | None:
    try:
        from src.llm import get_structured_model, to_text
        from src.schemas import WriterReview

        reviewer = get_structured_model("small", WriterReview)
        review_msg = reviewer.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a strict editor. Read the report and decide if it "
                        "needs revision. Look for: missing citations [N], unclear "
                        "structure (no H1, no sections), factual contradictions, "
                        "weak conclusion, off-topic content. Be conservative — only "
                        "ask for revision if a CONCRETE issue exists."
                    )
                ),
                HumanMessage(content=f"Report to review:\n\n{text}"),
            ]
        )
        if not getattr(review_msg, "needs_revision", False):
            return None
        suggestions = getattr(review_msg, "suggestions", "")
        issues = getattr(review_msg, "issues", []) or []
        feedback_block = "REVISION FEEDBACK:\n" + (suggestions or "")
        if issues:
            feedback_block += "\n\nSpecific issues:\n" + "\n".join(f"- {i}" for i in issues)
        revised_messages = base_messages + [
            HumanMessage(
                content=(
                    f"{feedback_block}\n\nRevise the previous draft addressing these issues. "
                    "Return the FULL revised markdown report."
                )
            )
        ]
        revised = llm.invoke(revised_messages)
        return to_text(getattr(revised, "content", revised))
    except Exception:
        return None


def _verify_claims(report: str, urls: list[str], language: str) -> dict | None:
    try:
        from src.llm import get_structured_model
        from src.schemas import ClaimVerification

        verifier = get_structured_model("small", ClaimVerification)
        sources_block = "\n".join(f"[{i+1}] {u}" for i, u in enumerate(urls))
        lang = "Use Korean for claim text and summary." if language == "ko" else "Use English."
        sys = SystemMessage(
            content=(
                "Extract the main factual claims from the report and analyze their support. "
                "For each claim, list which numbered sources [1], [2], ... support it. "
                "Mark risk: 'ok' (>=2 sources), 'single-source' (only 1), "
                "'unsupported' (no inline citation found nearby), or 'conflicting'. "
                "Also assign a 0-10 confidence: 10 = strongly verified by multiple "
                "authoritative sources, 5 = single source / unclear, 0 = no support. "
                f"{lang} Limit to the 6 most important claims."
            )
        )
        user = HumanMessage(content=f"Sources:\n{sources_block}\n\nReport:\n{report}")
        result = verifier.invoke([sys, user])
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
    except Exception:
        return None
    return None
