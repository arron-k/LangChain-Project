import sqlite3
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.schemas import JudgeScore


def _system(language: str) -> str:
    lang = "Comment in Korean." if language == "ko" else "Comment in English."
    return (
        "You are an expert research-report evaluator. Score the following report "
        "on five 0-10 criteria, plus an overall 0-10 score. "
        "Then write a short 1-2 sentence comment about its strengths and weaknesses. "
        "Be honest — do not inflate scores. "
        "Criteria: accuracy (facts), citations (sources cited well), structure "
        "(organization), readability (clarity), length_fit (length right for topic). "
        f"{lang}"
    )


def judge_report(topic: str, report: str, language: str = "en") -> JudgeScore | None:
    if not report.strip():
        return None
    try:
        from src.llm import get_structured_model

        judge = get_structured_model("small", JudgeScore)
        result = judge.invoke(
            [
                SystemMessage(content=_system(language)),
                HumanMessage(content=f"Topic: {topic}\n\nReport:\n{report}"),
            ]
        )
        if isinstance(result, JudgeScore):
            return result
        if isinstance(result, dict):
            return JudgeScore(**result)
    except Exception:
        return None
    return None


class JudgeStore:
    def __init__(self, db_path: str | Path):
        self.path = str(db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init()

    def _init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS judge_score (
                ts REAL NOT NULL,
                thread_id TEXT NOT NULL,
                topic TEXT,
                accuracy REAL, citations REAL, structure REAL,
                readability REAL, length_fit REAL, overall REAL,
                comment TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_judge_thread ON judge_score(thread_id)"
        )
        self.conn.commit()

    def submit(self, thread_id: str, score: JudgeScore, topic: str = "") -> None:
        self.conn.execute(
            "INSERT INTO judge_score "
            "(ts, thread_id, topic, accuracy, citations, structure, "
            "readability, length_fit, overall, comment) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                time.time(),
                thread_id,
                topic,
                score.accuracy,
                score.citations,
                score.structure,
                score.readability,
                score.length_fit,
                score.overall,
                score.comment,
            ),
        )
        self.conn.commit()

    def latest_for(self, thread_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT ts, accuracy, citations, structure, readability, "
            "length_fit, overall, comment FROM judge_score "
            "WHERE thread_id=? ORDER BY ts DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
        if not row:
            return None
        keys = ["ts", "accuracy", "citations", "structure", "readability", "length_fit", "overall", "comment"]
        return dict(zip(keys, row))

    def stats(self, since_seconds: float = 7 * 86400) -> dict:
        cutoff = time.time() - since_seconds
        row = self.conn.execute(
            "SELECT COUNT(*), AVG(overall), AVG(accuracy), AVG(citations), "
            "AVG(structure), AVG(readability), AVG(length_fit) "
            "FROM judge_score WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
        cnt = row[0] or 0
        if cnt == 0:
            return {"count": 0}
        return {
            "count": cnt,
            "overall": round(row[1] or 0, 2),
            "accuracy": round(row[2] or 0, 2),
            "citations": round(row[3] or 0, 2),
            "structure": round(row[4] or 0, 2),
            "readability": round(row[5] or 0, 2),
            "length_fit": round(row[6] or 0, 2),
        }
