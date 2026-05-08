import sqlite3
import time
from pathlib import Path


class ThreadMeta:
    def __init__(self, db_path: str | Path):
        self.path = str(db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init()

    def _init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_meta (
                thread_id TEXT PRIMARY KEY,
                display_name TEXT,
                tags TEXT,
                favorite INTEGER DEFAULT 0,
                updated_at REAL
            )
            """
        )
        self.conn.commit()

    def get(self, thread_id: str) -> dict:
        row = self.conn.execute(
            "SELECT thread_id, display_name, tags, favorite, updated_at "
            "FROM thread_meta WHERE thread_id=?",
            (thread_id,),
        ).fetchone()
        if not row:
            return {
                "thread_id": thread_id,
                "display_name": "",
                "tags": [],
                "favorite": False,
                "updated_at": None,
            }
        return {
            "thread_id": row[0],
            "display_name": row[1] or "",
            "tags": [t for t in (row[2] or "").split(",") if t.strip()],
            "favorite": bool(row[3]),
            "updated_at": row[4],
        }

    def all(self) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT thread_id, display_name, tags, favorite, updated_at FROM thread_meta"
        ).fetchall()
        return {
            r[0]: {
                "thread_id": r[0],
                "display_name": r[1] or "",
                "tags": [t for t in (r[2] or "").split(",") if t.strip()],
                "favorite": bool(r[3]),
                "updated_at": r[4],
            }
            for r in rows
        }

    def upsert(
        self,
        thread_id: str,
        display_name: str | None = None,
        tags: list[str] | None = None,
        favorite: bool | None = None,
    ) -> None:
        cur = self.get(thread_id)
        new_name = display_name if display_name is not None else cur["display_name"]
        new_tags = tags if tags is not None else cur["tags"]
        new_fav = favorite if favorite is not None else cur["favorite"]
        self.conn.execute(
            "INSERT OR REPLACE INTO thread_meta "
            "(thread_id, display_name, tags, favorite, updated_at) "
            "VALUES (?,?,?,?,?)",
            (
                thread_id,
                new_name,
                ",".join(new_tags),
                1 if new_fav else 0,
                time.time(),
            ),
        )
        self.conn.commit()

    def delete(self, thread_id: str) -> None:
        self.conn.execute("DELETE FROM thread_meta WHERE thread_id=?", (thread_id,))
        self.conn.commit()

    def toggle_favorite(self, thread_id: str) -> bool:
        cur = self.get(thread_id)
        self.upsert(thread_id, favorite=not cur["favorite"])
        return not cur["favorite"]
