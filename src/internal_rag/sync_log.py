import os
import sqlite3
import time
from pathlib import Path
from typing import Optional


DEFAULT_PATH = os.getenv("SYNC_LOG_DB", "./sync_log.sqlite")


class SyncLog:
    def __init__(self, db_path: str | Path | None = None):
        self.path = str(db_path or DEFAULT_PATH)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init()

    def _init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_log (
                source TEXT PRIMARY KEY,
                last_synced_at REAL NOT NULL,
                docs INTEGER DEFAULT 0,
                chunks INTEGER DEFAULT 0,
                elapsed_sec REAL DEFAULT 0,
                last_error TEXT
            )
            """
        )
        self.conn.commit()

    def record(
        self,
        source: str,
        docs: int = 0,
        chunks: int = 0,
        elapsed_sec: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_log (source, last_synced_at, docs, chunks, elapsed_sec, last_error) "
            "VALUES (?,?,?,?,?,?)",
            (source, time.time(), int(docs), int(chunks), float(elapsed_sec), error),
        )
        self.conn.commit()

    def get(self, source: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT source, last_synced_at, docs, chunks, elapsed_sec, last_error "
            "FROM sync_log WHERE source=?",
            (source,),
        ).fetchone()
        if not row:
            return None
        keys = ["source", "last_synced_at", "docs", "chunks", "elapsed_sec", "last_error"]
        return dict(zip(keys, row))

    def all(self) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT source, last_synced_at, docs, chunks, elapsed_sec, last_error FROM sync_log"
        ).fetchall()
        keys = ["source", "last_synced_at", "docs", "chunks", "elapsed_sec", "last_error"]
        return {r[0]: dict(zip(keys, r)) for r in rows}

    def reset(self, source: Optional[str] = None) -> None:
        if source:
            self.conn.execute("DELETE FROM sync_log WHERE source=?", (source,))
        else:
            self.conn.execute("DELETE FROM sync_log")
        self.conn.commit()


def format_relative(ts: float) -> str:
    """Returns '5 minutes ago' style string."""
    diff = time.time() - ts
    if diff < 0:
        return "just now"
    if diff < 60:
        return f"{int(diff)}s ago"
    if diff < 3600:
        return f"{int(diff/60)}m ago"
    if diff < 86400:
        return f"{int(diff/3600)}h ago"
    if diff < 86400 * 30:
        return f"{int(diff/86400)}d ago"
    return time.strftime("%Y-%m-%d", time.localtime(ts))
