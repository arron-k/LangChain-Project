import time
from typing import Iterable, Optional

from src.internal_rag.connectors.base import IngestDocument


def _get_connector(name: str):
    if name == "wiki":
        from src.internal_rag.connectors.confluence import ConfluenceConnector

        return ConfluenceConnector()
    if name == "slack":
        from src.internal_rag.connectors.slack import SlackConnector

        return SlackConnector()
    raise ValueError(f"Unknown source: {name}")


def _chunk_documents(docs: Iterable[IngestDocument], chunk_size: int = 400, overlap: int = 40):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    for d in docs:
        chunks = splitter.split_text(d.content)
        for i, chunk in enumerate(chunks):
            texts.append(chunk)
            metadatas.append(
                {
                    "source": d.source,
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "url": d.url,
                    "chunk_index": i,
                    **{k: v for k, v in (d.metadata or {}).items() if isinstance(v, (str, int, float, bool))},
                }
            )
            ids.append(f"{d.doc_id}::chunk:{i}")
    return texts, metadatas, ids


def ingest(
    sources: Optional[list[str]] = None,
    reset: bool = False,
    persist_dir: Optional[str] = None,
    incremental: bool = False,
) -> dict:
    """Run ingestion for the given sources, return per-source stats.

    Modes:
      - reset=True: drop whole collection (all sources) and rebuild.
      - reset=False, incremental=False: drop this source's chunks, refetch all, rebuild this source.
      - reset=False, incremental=True: fetch only documents modified after last_synced_at;
        delete only those documents' chunks then upsert. Other sources untouched.
    """
    sources = sources or ["wiki"]
    from src.internal_rag.sync_log import SyncLog
    from src.internal_rag.vector_store import get_chroma, reset_collection

    if reset:
        reset_collection(persist_dir=persist_dir)

    store = get_chroma(persist_dir=persist_dir)
    sync_log = SyncLog()
    stats: dict = {}

    for src in sources:
        t0 = time.time()
        added = 0
        failed = 0
        docs = []
        texts: list[str] = []
        last_error: Optional[str] = None

        try:
            if reset:
                pass
            elif incremental:
                pass
            else:
                try:
                    store._collection.delete(where={"source": src})
                except Exception:
                    pass

            since_ts = None
            if incremental:
                rec = sync_log.get(src)
                if rec and rec.get("last_synced_at"):
                    since_ts = float(rec["last_synced_at"])

            connector = _get_connector(src)
            docs = list(connector.fetch_documents(since_ts=since_ts))

            if incremental and docs:
                doc_ids = [d.doc_id for d in docs]
                try:
                    store._collection.delete(where={"doc_id": {"$in": doc_ids}})
                except Exception:
                    pass

            texts, metadatas, ids = _chunk_documents(docs)

            batch = 32
            for i in range(0, len(texts), batch):
                try:
                    store.add_texts(
                        texts=texts[i : i + batch],
                        metadatas=metadatas[i : i + batch],
                        ids=ids[i : i + batch],
                    )
                    added += len(texts[i : i + batch])
                except Exception:
                    for j in range(i, min(i + batch, len(texts))):
                        try:
                            store.add_texts(texts=[texts[j]], metadatas=[metadatas[j]], ids=[ids[j]])
                            added += 1
                        except Exception:
                            failed += 1
        except Exception as e:
            last_error = str(e)[:300]

        elapsed = round(time.time() - t0, 2)
        stats[src] = {
            "docs": len(docs),
            "chunks_total": len(texts),
            "chunks_added": added,
            "chunks_failed": failed,
            "elapsed_sec": elapsed,
            "error": last_error,
        }
        sync_log.record(
            source=src,
            docs=len(docs),
            chunks=added,
            elapsed_sec=elapsed,
            error=last_error,
        )

    return stats
