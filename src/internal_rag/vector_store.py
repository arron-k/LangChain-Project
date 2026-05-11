import os
from pathlib import Path
from typing import Optional


DEFAULT_PERSIST_DIR = os.getenv("INTERNAL_VECTOR_DB", "./internal_chroma")
COLLECTION_NAME = "internal_docs"


def get_chroma(embedding_function=None, persist_dir: Optional[str] = None):
    from langchain_chroma import Chroma

    path = Path(persist_dir or DEFAULT_PERSIST_DIR)
    path.mkdir(parents=True, exist_ok=True)
    if embedding_function is None:
        from src.internal_rag.embeddings import get_embeddings

        embedding_function = get_embeddings()
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embedding_function,
        persist_directory=str(path),
    )


def reset_collection(persist_dir: Optional[str] = None) -> None:
    from langchain_chroma import Chroma

    path = Path(persist_dir or DEFAULT_PERSIST_DIR)
    path.mkdir(parents=True, exist_ok=True)
    try:
        from src.internal_rag.embeddings import get_embeddings

        store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embeddings(),
            persist_directory=str(path),
        )
        store.delete_collection()
    except Exception:
        pass


def collection_stats(persist_dir: Optional[str] = None) -> dict:
    try:
        store = get_chroma(persist_dir=persist_dir)
        col = store._collection
        return {
            "count": col.count(),
            "path": str(Path(persist_dir or DEFAULT_PERSIST_DIR).absolute()),
        }
    except Exception as e:
        return {"count": 0, "error": str(e)}


def count_by_source(persist_dir: Optional[str] = None) -> dict[str, int]:
    """Return per-source chunk counts. Empty dict on failure."""
    try:
        store = get_chroma(persist_dir=persist_dir)
        col = store._collection
        counts: dict[str, int] = {}
        for src in ("wiki", "slack", "jira"):
            try:
                got = col.get(where={"source": src}, include=[])
                ids = got.get("ids", []) if isinstance(got, dict) else []
                counts[src] = len(ids)
            except Exception:
                counts[src] = 0
        return counts
    except Exception:
        return {}
