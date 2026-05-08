import sqlite3
import time
from pathlib import Path


class FeedbackStore:
    def __init__(self, db_path: str | Path):
        self.path = str(db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init()

    def _init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                ts REAL NOT NULL,
                thread_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT,
                topic TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_thread ON feedback(thread_id)"
        )
        self.conn.commit()

    def submit(self, thread_id: str, rating: int, comment: str = "", topic: str = "") -> None:
        self.conn.execute(
            "INSERT INTO feedback (ts, thread_id, rating, comment, topic) VALUES (?,?,?,?,?)",
            (time.time(), thread_id, int(rating), comment, topic),
        )
        self.conn.commit()

    def latest_for(self, thread_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT ts, rating, comment, topic FROM feedback "
            "WHERE thread_id=? ORDER BY ts DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
        if not row:
            return None
        return {"ts": row[0], "rating": row[1], "comment": row[2], "topic": row[3]}

    def stats(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) FROM feedback"
        ).fetchone()
        total, pos, neg = row
        return {
            "total": total or 0,
            "positive": pos or 0,
            "negative": neg or 0,
        }
