import sqlite3
import time
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class UsageStore:
    def __init__(self, db_path: str | Path):
        self.path = str(db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init()

    def _init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_log (
                ts REAL NOT NULL,
                provider TEXT,
                model TEXT,
                role TEXT,
                latency REAL,
                ok INTEGER
            )
            """
        )
        self.conn.commit()

    def log(self, provider: str, model: str, role: str, latency: float, ok: bool) -> None:
        self.conn.execute(
            "INSERT INTO usage_log (ts, provider, model, role, latency, ok) VALUES (?,?,?,?,?,?)",
            (time.time(), provider, model, role, latency, 1 if ok else 0),
        )
        self.conn.commit()

    def stats(self, since_seconds: float = 86400) -> dict:
        cutoff = time.time() - since_seconds
        rows = self.conn.execute(
            "SELECT provider, model, role, COUNT(*), AVG(latency), SUM(ok) "
            "FROM usage_log WHERE ts >= ? GROUP BY provider, model, role "
            "ORDER BY COUNT(*) DESC",
            (cutoff,),
        ).fetchall()
        total = self.conn.execute(
            "SELECT COUNT(*), SUM(ok) FROM usage_log WHERE ts >= ?", (cutoff,)
        ).fetchone()
        return {
            "total_calls": total[0] or 0,
            "successful_calls": total[1] or 0,
            "by_combo": [
                {
                    "provider": r[0],
                    "model": r[1],
                    "role": r[2],
                    "count": r[3],
                    "avg_latency": round(r[4] or 0, 2),
                    "ok": r[5] or 0,
                }
                for r in rows
            ],
        }

    def total_today(self) -> int:
        return self.stats(since_seconds=86400)["total_calls"]


class UsageCallback(BaseCallbackHandler):
    def __init__(self, store: UsageStore, provider: str, model: str, role: str):
        self.store = store
        self.provider = provider
        self.model = model
        self.role = role
        self._start: dict[str, float] = {}

    def on_llm_start(self, serialized: dict, prompts: list[str], *, run_id, **kwargs: Any) -> None:
        self._start[str(run_id)] = time.time()

    def on_llm_end(self, response: Any, *, run_id, **kwargs: Any) -> None:
        latency = time.time() - self._start.pop(str(run_id), time.time())
        self.store.log(self.provider, self.model, self.role, latency, ok=True)

    def on_llm_error(self, error: BaseException, *, run_id, **kwargs: Any) -> None:
        latency = time.time() - self._start.pop(str(run_id), time.time())
        self.store.log(self.provider, self.model, self.role, latency, ok=False)
