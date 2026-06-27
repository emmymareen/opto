"""Telemetry + enterprise audit logging.

Persists one row per request to SQLite for the dashboard, and appends an
immutable JSONL audit line. By default no raw prompt content is stored
(``redact_content_in_logs``), which matters for enterprise/regulated use.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import Lock

from opto.types import PipelineReport

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    original_tokens INTEGER NOT NULL,
    compressed_tokens INTEGER NOT NULL,
    saved_tokens INTEGER NOT NULL,
    saved_fraction REAL NOT NULL,
    chunks_total INTEGER NOT NULL,
    chunks_dropped INTEGER NOT NULL,
    compressed INTEGER NOT NULL,
    held_out INTEGER NOT NULL,
    backed_off INTEGER NOT NULL,
    quality_risk REAL NOT NULL,
    by_kind TEXT NOT NULL
);
"""


class Telemetry:
    def __init__(self, db_path: Path, audit_path: Path, redact: bool = True):
        self.db_path = Path(db_path)
        self.audit_path = Path(audit_path)
        self.redact = redact
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def record(self, report: PipelineReport) -> None:
        row = (
            time.time(),
            report.original_tokens,
            report.compressed_tokens,
            report.saved_tokens,
            report.saved_fraction,
            report.chunks_total,
            report.chunks_dropped,
            int(report.compressed),
            int(report.held_out),
            int(report.backed_off),
            report.quality_risk,
            json.dumps(report.by_kind),
        )
        with self._lock, self._connect() as con:
            con.execute(
                """INSERT INTO requests
                   (ts, original_tokens, compressed_tokens, saved_tokens, saved_fraction,
                    chunks_total, chunks_dropped, compressed, held_out, backed_off,
                    quality_risk, by_kind)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                row,
            )
        self._append_audit(report)

    def _append_audit(self, report: PipelineReport) -> None:
        entry = {
            "ts": time.time(),
            "original_tokens": report.original_tokens,
            "compressed_tokens": report.compressed_tokens,
            "saved_tokens": report.saved_tokens,
            "saved_fraction": round(report.saved_fraction, 4),
            "compressed": report.compressed,
            "held_out": report.held_out,
            "backed_off": report.backed_off,
            "quality_risk": report.quality_risk,
            "by_kind": report.by_kind,
        }
        if self.redact:
            entry["content_redacted"] = True
        with self._lock:
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def summary(self) -> dict:
        with self._connect() as con:
            cur = con.execute(
                """SELECT COUNT(*), COALESCE(SUM(original_tokens),0),
                          COALESCE(SUM(compressed_tokens),0),
                          COALESCE(SUM(saved_tokens),0),
                          COALESCE(SUM(backed_off),0),
                          COALESCE(SUM(held_out),0)
                   FROM requests"""
            )
            n, orig, comp, saved, backed, held = cur.fetchone()
        frac = (saved / orig) if orig else 0.0
        return {
            "requests": n,
            "original_tokens": orig,
            "compressed_tokens": comp,
            "saved_tokens": saved,
            "saved_fraction": round(frac, 4),
            "backed_off": backed,
            "held_out": held,
        }

    def recent(self, limit: int = 50) -> list[dict]:
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            cur = con.execute(
                "SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]
