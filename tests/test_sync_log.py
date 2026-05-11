import time
from pathlib import Path

from src.internal_rag.sync_log import SyncLog, format_relative


def test_sync_log_record_and_get(tmp_path: Path):
    log = SyncLog(tmp_path / "s.sqlite")
    log.record("wiki", docs=10, chunks=120, elapsed_sec=4.5)
    row = log.get("wiki")
    assert row["source"] == "wiki"
    assert row["docs"] == 10
    assert row["chunks"] == 120
    assert row["elapsed_sec"] == 4.5
    assert row["last_error"] is None
    assert abs(row["last_synced_at"] - time.time()) < 5


def test_sync_log_upsert_overwrites(tmp_path: Path):
    log = SyncLog(tmp_path / "s.sqlite")
    log.record("wiki", docs=5)
    log.record("wiki", docs=99)
    assert log.get("wiki")["docs"] == 99


def test_sync_log_all_returns_dict(tmp_path: Path):
    log = SyncLog(tmp_path / "s.sqlite")
    log.record("wiki", docs=1)
    log.record("slack", docs=2)
    out = log.all()
    assert set(out.keys()) == {"wiki", "slack"}


def test_sync_log_records_error(tmp_path: Path):
    log = SyncLog(tmp_path / "s.sqlite")
    log.record("wiki", error="auth failed")
    assert log.get("wiki")["last_error"] == "auth failed"


def test_sync_log_reset_specific_source(tmp_path: Path):
    log = SyncLog(tmp_path / "s.sqlite")
    log.record("wiki", docs=1)
    log.record("slack", docs=1)
    log.reset("wiki")
    assert log.get("wiki") is None
    assert log.get("slack") is not None


def test_format_relative_buckets():
    now = time.time()
    assert "s ago" in format_relative(now - 10)
    assert "m ago" in format_relative(now - 120)
    assert "h ago" in format_relative(now - 7200)
    assert "d ago" in format_relative(now - 86400 * 3)
