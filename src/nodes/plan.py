import json
import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def _system_prompt(language: str, n: int, persona: str = "") -> str:
    lang_line = (
        "Write the sub-questions in Korean."
        if language == "ko"
        else "Write the sub-questions in English."
    )
    base = (
        f"You decompose a research topic into EXACTLY {n} focused sub-questions. "
        f"{lang_line} "
        'Return ONLY JSON of the form {"sub_questions": ["q1", "q2", ...]}. '
        "No prose, no code fences."
    )
    return f"{persona}\n\n{base}".strip() if persona else base


def plan_node(state: dict, llm: Optional[BaseChatModel] = None) -> dict:
    topic = state.get("topic", "")
    language = state.get("language", "en")
    n = max(1, min(int(state.get("num_questions", 3)), 6))

    user_parts = [f"Topic: {topic}"]
    prev_reflection = state.get("reflection", "")
    if prev_reflection and state.get("iteration", 0) > 0:
        user_parts.append(f"Previous reflection (revise plan based on this):\n{prev_reflection}")

    if state.get("use_lessons"):
        from src.lessons import relevant_lessons

        lessons = relevant_lessons(topic, k=3)
        if lessons:
            tips = "\n".join(f"- {l.get('reflection', '')[:200]}" for l in lessons)
            user_parts.append(f"Lessons from past similar topics:\n{tips}")

    messages = [
        SystemMessage(content=_system_prompt(language, n, persona=state.get("persona", ""))),
        HumanMessage(content="\n\n".join(user_parts)),
    ]

    if llm is None:
        try:
            from src.llm import get_structured_model
            from src.schemas import PlanOutput

            structured = get_structured_model("small", PlanOutput)
            result = structured.invoke(messages)
            qs = (result.sub_questions or [])[:n] if hasattr(result, "sub_questions") else []
            if qs:
                return {"sub_questions": qs}
        except Exception:
            pass
        from src.llm import get_chat_model

        llm = get_chat_model("small")

    msg = llm.invoke(messages)
    from src.llm import to_text

    text = to_text(getattr(msg, "content", msg))
    sub_questions = _parse_questions(text, fallback_topic=topic, n=n)
    return {"sub_questions": sub_questions}


def _parse_questions(text: str, fallback_topic: str, n: int = 3) -> list[str]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            qs = data.get("sub_questions")
            if isinstance(qs, list) and qs:
                return [str(q) for q in qs[:n]]
        except json.JSONDecodeError:
            pass
    return [f"What is {fallback_topic}?"]
