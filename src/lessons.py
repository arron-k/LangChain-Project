import json
from datetime import datetime
from pathlib import Path

LESSONS_PATH = Path(__file__).resolve().parent.parent / "lessons.json"


def load_lessons(path: Path = LESSONS_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_lesson(topic: str, reflection: str, sufficient: bool, path: Path = LESSONS_PATH) -> None:
    items = load_lessons(path)
    items.append(
        {
            "topic": topic,
            "reflection": reflection[:500],
            "sufficient": bool(sufficient),
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
        }
    )
    items = items[-50:]
    try:
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    except OSError:
        pass


def save_reflexion(memo: dict, path: Path = LESSONS_PATH) -> None:
    """Save a structured ReflexionMemo dict alongside text lessons."""
    items = load_lessons(path)
    items.append(
        {
            "topic": memo.get("topic", ""),
            "structured": memo,
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
        }
    )
    items = items[-50:]
    try:
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    except OSError:
        pass


def relevant_reflexions(topic: str, k: int = 3, path: Path = LESSONS_PATH) -> list[dict]:
    """Return relevant structured reflexion memos for a topic."""
    items = load_lessons(path)
    topic_words = set(topic.lower().split())
    scored = []
    for it in items:
        if "structured" not in it:
            continue
        words = set((it.get("topic") or "").lower().split())
        overlap = len(topic_words & words)
        if overlap > 0:
            scored.append((overlap, it["structured"]))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:k]]


def relevant_lessons(topic: str, k: int = 3, path: Path = LESSONS_PATH) -> list[dict]:
    items = load_lessons(path)
    topic_words = set(topic.lower().split())
    scored = []
    for it in items:
        words = set((it.get("topic") or "").lower().split())
        overlap = len(topic_words & words)
        if overlap > 0:
            scored.append((overlap, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:k]]
