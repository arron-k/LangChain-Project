import os
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

Role = Literal["small", "large", "default"]

DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))


def to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text", ""))
            else:
                parts.append(str(c))
        return "".join(parts)
    return str(content)


def _gemini(model: str) -> tuple[BaseChatModel, str]:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return (
        ChatGoogleGenerativeAI(
            model=model, temperature=0, max_retries=2, timeout=DEFAULT_TIMEOUT
        ),
        f"google:{model}",
    )


def _anthropic(model: str) -> tuple[BaseChatModel, str]:
    from langchain_anthropic import ChatAnthropic

    return (
        ChatAnthropic(model_name=model, temperature=0, timeout=DEFAULT_TIMEOUT),
        f"anthropic:{model}",
    )


def _groq(model: str) -> tuple[BaseChatModel, str]:
    from langchain_groq import ChatGroq

    return (
        ChatGroq(model_name=model, temperature=0, timeout=DEFAULT_TIMEOUT),
        f"groq:{model}",
    )


def _ollama(model: str) -> tuple[BaseChatModel, str]:
    from langchain_ollama import ChatOllama

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return (
        ChatOllama(model=model, temperature=0, base_url=base_url),
        f"ollama:{model}",
    )


def get_embeddings():
    """Return an embeddings object based on OLLAMA_EMBED_MODEL.
    Used by the internal RAG ingestion / retriever.
    """
    from langchain_ollama import OllamaEmbeddings

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    return OllamaEmbeddings(model=model, base_url=base_url)


def _candidates(role: Role) -> list[tuple[BaseChatModel, str]]:
    out: list[tuple[BaseChatModel, str]] = []

    if os.getenv("GOOGLE_API_KEY"):
        small = os.getenv("GEMINI_MODEL_SMALL", "gemini-flash-lite-latest")
        large = os.getenv("GEMINI_MODEL_LARGE", "gemini-2.5-flash")
        m = small if role == "small" else (large if role == "large" else os.getenv("GEMINI_MODEL", small))
        out.append(_gemini(m))

    if os.getenv("ANTHROPIC_API_KEY"):
        small = os.getenv("ANTHROPIC_MODEL_SMALL", "claude-haiku-4-5-20251001")
        large = os.getenv("ANTHROPIC_MODEL_LARGE", "claude-sonnet-4-5")
        m = small if role == "small" else (large if role == "large" else small)
        out.append(_anthropic(m))

    if os.getenv("GROQ_API_KEY"):
        small = os.getenv("GROQ_MODEL_SMALL", "llama-3.1-8b-instant")
        large = os.getenv("GROQ_MODEL_LARGE", "llama-3.3-70b-versatile")
        m = small if role == "small" else (large if role == "large" else small)
        out.append(_groq(m))

    if os.getenv("OLLAMA_BASE_URL"):
        small = os.getenv("OLLAMA_MODEL_SMALL", os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b"))
        large = os.getenv("OLLAMA_MODEL_LARGE", os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b"))
        m = small if role == "small" else (large if role == "large" else small)
        out.append(_ollama(m))

    return out


def _attach_usage(llm: BaseChatModel, label: str, role: Role) -> Runnable:
    store = _usage_store()
    if store is None:
        return llm
    from src.usage import UsageCallback

    provider, model = label.split(":", 1)
    cb = UsageCallback(store, provider=provider, model=model, role=role)
    return llm.with_config({"callbacks": [cb]})


_USAGE_STORE = None


def _usage_store():
    global _USAGE_STORE
    if _USAGE_STORE is None:
        try:
            from src.usage import UsageStore

            db_path = os.getenv("USAGE_DB", str(Path(__file__).resolve().parent.parent / "usage.sqlite"))
            _USAGE_STORE = UsageStore(db_path)
        except Exception:
            _USAGE_STORE = False
    return _USAGE_STORE if _USAGE_STORE is not False else None


def get_chat_model(role: Role = "default", prefer: str | None = None) -> Runnable:
    cands = _candidates(role)
    if not cands:
        raise RuntimeError(
            "No LLM API key found. Set GOOGLE_API_KEY / ANTHROPIC_API_KEY / GROQ_API_KEY."
        )
    if prefer:
        cands = sorted(cands, key=lambda c: 0 if c[1].startswith(prefer + ":") else 1)

    wrapped = [_attach_usage(m, lbl, role) for (m, lbl) in cands]
    primary = wrapped[0]
    fallbacks = wrapped[1:]
    runnable = primary.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)
    if fallbacks:
        runnable = runnable.with_fallbacks(fallbacks)
    return runnable


def get_structured_model(role: Role, schema, prefer: str | None = None):
    cands = _candidates(role)
    if not cands:
        raise RuntimeError("No LLM API key found.")
    if prefer:
        cands = sorted(cands, key=lambda c: 0 if c[1].startswith(prefer + ":") else 1)
    wrapped = []
    for m, lbl in cands:
        try:
            structured = m.with_structured_output(schema)
        except Exception:
            continue
        wrapped.append(_attach_usage(structured, lbl, role))
    if not wrapped:
        raise RuntimeError("No model supports structured output.")
    primary = wrapped[0]
    fallbacks = wrapped[1:]
    runnable = primary.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)
    if fallbacks:
        runnable = runnable.with_fallbacks(fallbacks)
    return runnable


def available_providers() -> list[str]:
    out = []
    if os.getenv("GOOGLE_API_KEY"):
        out.append("google")
    if os.getenv("ANTHROPIC_API_KEY"):
        out.append("anthropic")
    if os.getenv("GROQ_API_KEY"):
        out.append("groq")
    if os.getenv("OLLAMA_BASE_URL"):
        out.append("ollama")
    return out


def langsmith_status() -> dict:
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    tracing = os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2")
    project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default"
    enabled = bool(api_key) and (tracing or "").lower() in ("true", "1")
    return {
        "enabled": enabled,
        "has_key": bool(api_key),
        "project": project,
        "url": f"https://smith.langchain.com/o/-/projects/p/{project}" if enabled else "https://smith.langchain.com/",
    }


def secrets_status() -> dict[str, dict]:
    def mask(v: str | None) -> str | None:
        if not v:
            return None
        if len(v) <= 8:
            return "*" * len(v)
        return v[:4] + "*" * (len(v) - 8) + v[-4:]

    return {
        "GOOGLE_API_KEY": {"set": bool(os.getenv("GOOGLE_API_KEY")), "masked": mask(os.getenv("GOOGLE_API_KEY"))},
        "ANTHROPIC_API_KEY": {"set": bool(os.getenv("ANTHROPIC_API_KEY")), "masked": mask(os.getenv("ANTHROPIC_API_KEY"))},
        "GROQ_API_KEY": {"set": bool(os.getenv("GROQ_API_KEY")), "masked": mask(os.getenv("GROQ_API_KEY"))},
        "TAVILY_API_KEY": {"set": bool(os.getenv("TAVILY_API_KEY")), "masked": mask(os.getenv("TAVILY_API_KEY"))},
        "OLLAMA_BASE_URL": {"set": bool(os.getenv("OLLAMA_BASE_URL")), "masked": os.getenv("OLLAMA_BASE_URL") or None},
        "CONFLUENCE_URL": {"set": bool(os.getenv("CONFLUENCE_URL")), "masked": os.getenv("CONFLUENCE_URL") or None},
        "CONFLUENCE_API_TOKEN": {"set": bool(os.getenv("CONFLUENCE_API_TOKEN")), "masked": mask(os.getenv("CONFLUENCE_API_TOKEN"))},
    }
