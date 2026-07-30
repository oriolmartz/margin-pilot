"""
audit.py

A real audit table (SQLite), keyed by thread_id, one row per request that
reaches the approval graph -- its status moves pending -> approved/rejected,
or is auto_approved/error in one step. This is what a compliance review
would query. Phase 2's traceability_log.jsonl is unrelated and unchanged --
it logs the plain /recommend endpoint, which never goes through approval.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "audit.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            thread_id TEXT PRIMARY KEY,
            created_at TEXT,
            updated_at TEXT,
            message TEXT,
            product_id TEXT,
            recommended_price REAL,
            price_change_pct REAL,
            requires_approval INTEGER,
            approval_reason TEXT,
            status TEXT,
            approved_by TEXT,
            raw_json TEXT
        )
        """
    )
    return conn


def upsert_pending(thread_id: str, message: str, recommendation: dict, price_change_pct: float, reason: str) -> None:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO audit_log (thread_id, created_at, updated_at, message, product_id, recommended_price,
                                price_change_pct, requires_approval, approval_reason, status, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 'pending', ?)
        ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at
        """,
        (
            thread_id, now, now, message, recommendation["product_id"], recommendation["recommended_price"],
            price_change_pct, reason, json.dumps(recommendation, default=str),
        ),
    )
    conn.commit()
    conn.close()


def record_auto_approved(thread_id: str, message: str, recommendation: dict, price_change_pct: float) -> None:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO audit_log (thread_id, created_at, updated_at, message, product_id, recommended_price,
                                price_change_pct, requires_approval, status, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'auto_approved', ?)
        ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at, status = 'auto_approved'
        """,
        (
            thread_id, now, now, message, recommendation["product_id"], recommendation["recommended_price"],
            price_change_pct, json.dumps(recommendation, default=str),
        ),
    )
    conn.commit()
    conn.close()


def record_error(thread_id: str, message: str, error: str) -> None:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO audit_log (thread_id, created_at, updated_at, message, requires_approval, status, raw_json)
        VALUES (?, ?, ?, ?, 0, 'error', ?)
        ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at, status = 'error'
        """,
        (thread_id, now, now, message, json.dumps({"error": error})),
    )
    conn.commit()
    conn.close()


def record_decision(thread_id: str, approved: bool, approved_by: str) -> None:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE audit_log SET status = ?, approved_by = ?, updated_at = ? WHERE thread_id = ?",
        ("approved" if approved else "rejected", approved_by, now, thread_id),
    )
    conn.commit()
    conn.close()


def read_recent(limit: int = 20) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def read_pending() -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log WHERE status = 'pending' ORDER BY created_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
