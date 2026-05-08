import time
from typing import Any


def list_thread_ids(saver) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()

    storage = getattr(saver, "storage", None)
    if isinstance(storage, dict):
        for tid in storage.keys():
            if tid not in seen_set:
                seen.append(tid)
                seen_set.add(tid)
        return seen

    conn = getattr(saver, "conn", None)
    if conn is not None:
        try:
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT thread_id FROM checkpoints "
                "GROUP BY thread_id ORDER BY MAX(checkpoint_id) DESC"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        except Exception:
            pass

    try:
        for tup in saver.list(None):
            tid = (tup.config or {}).get("configurable", {}).get("thread_id")
            if tid and tid not in seen_set:
                seen.append(tid)
                seen_set.add(tid)
    except Exception:
        return []
    return seen


def delete_thread(saver, thread_id: str) -> bool:
    storage = getattr(saver, "storage", None)
    if isinstance(storage, dict):
        existed = thread_id in storage
        storage.pop(thread_id, None)
        for attr in ("writes", "blobs"):
            sub = getattr(saver, attr, None)
            if isinstance(sub, dict):
                sub.pop(thread_id, None)
        return existed

    conn = getattr(saver, "conn", None)
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        for table in ("checkpoints", "writes", "checkpoint_blobs", "checkpoint_writes"):
            try:
                cur.execute(f"DELETE FROM {table} WHERE thread_id=?", (thread_id,))
            except Exception:
                pass
        conn.commit()
        return True
    except Exception:
        return False


def delete_threads_older_than(saver, max_age_seconds: float) -> int:
    conn = getattr(saver, "conn", None)
    if conn is None:
        return 0
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT thread_id, MAX(checkpoint_id) as latest "
            "FROM checkpoints GROUP BY thread_id"
        ).fetchall()
    except Exception:
        return 0

    cutoff_ms = (time.time() - max_age_seconds) * 1000
    deleted = 0
    for tid, latest in rows:
        ts_ms = _checkpoint_id_to_ts(latest)
        if ts_ms is None:
            continue
        if ts_ms < cutoff_ms:
            if delete_thread(saver, tid):
                deleted += 1
    return deleted


def _checkpoint_id_to_ts(cid) -> float | None:
    if not cid:
        return None
    s = str(cid)
    try:
        return int(s.split("-")[0]) / 1.0
    except Exception:
        return None


def thread_summaries(graph, saver) -> list[dict[str, Any]]:
    out = []
    for tid in list_thread_ids(saver):
        try:
            snap = graph.get_state({"configurable": {"thread_id": tid}})
            v = snap.values or {}
            out.append(
                {
                    "thread_id": tid,
                    "topic": v.get("topic") or "(empty)",
                    "iteration": v.get("iteration", 0),
                    "sufficient": bool(v.get("sufficient", False)),
                    "has_report": bool(v.get("final_report")),
                    "next": list(snap.next or []),
                }
            )
        except Exception:
            continue
    return out
