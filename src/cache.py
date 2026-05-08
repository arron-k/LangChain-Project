import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional


class SearchCache:
    def __init__(self, db_path: str | Path, ttl_seconds: int = 24 * 3600):
        self.path = str(db_path)
        self.ttl = ttl_seconds
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init()

    def _init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self.conn.commit()

    @staticmethod
    def _key(query: str, opts: dict) -> str:
        h = hashlib.sha256()
        h.update(query.encode("utf-8"))
        h.update(json.dumps(opts, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        return h.hexdigest()

    def get(self, query: str, opts: dict) -> Optional[list[dict]]:
        key = self._key(query, opts)
        row = self.conn.execute(
            "SELECT payload, created_at FROM search_cache WHERE key=?", (key,)
        ).fetchone()
        if not row:
            return None
        payload, created = row
        if time.time() - created > self.ttl:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def set(self, query: str, opts: dict, value: list[dict]) -> None:
        key = self._key(query, opts)
        self.conn.execute(
            "INSERT OR REPLACE INTO search_cache (key, payload, created_at) VALUES (?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )
        self.conn.commit()

    def stats(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM search_cache"
        ).fetchone()
        cnt, oldest, newest = row
        live = self.conn.execute(
            "SELECT COUNT(*) FROM search_cache WHERE created_at > ?",
            (time.time() - self.ttl,),
        ).fetchone()[0]
        return {"count": cnt or 0, "live": live or 0, "oldest": oldest, "newest": newest}

    def clear(self) -> None:
        self.conn.execute("DELETE FROM search_cache")
        self.conn.commit()


def with_cache(search_fn, cache: SearchCache, opts: dict):
    def _wrapped(query: str) -> list[dict]:
        cached = cache.get(query, opts)
        if cached is not None:
            return cached
        result = search_fn(query)
        cache.set(query, opts, result)
        return result

    _wrapped._cache = cache  # type: ignore[attr-defined]
    return _wrapped
