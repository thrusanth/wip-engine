"""SQLite WAL-backed audit store for API Bouncer rejections and reconciliation logs."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

BOUNCER_DB_PATH = os.getenv("BOUNCER_BUFFER_PATH", "bouncer_audit.db")


def _connect(db_path: str = BOUNCER_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_bouncer_buffer(db_path: str = BOUNCER_DB_PATH) -> sqlite3.Connection:
    conn = _connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rejection_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            client_ip TEXT,
            path TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            detail TEXT,
            payload_preview TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_log (
            trace_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            sku TEXT NOT NULL,
            ean TEXT,
            status TEXT NOT NULL,
            format_alert TEXT,
            shop_floor_action TEXT,
            payload_json TEXT NOT NULL
        );
        """
    )
    return conn


def record_rejection(
    *,
    path: str,
    reason_code: str,
    detail: str | None = None,
    client_ip: str | None = None,
    payload_preview: str | None = None,
    db_path: str = BOUNCER_DB_PATH,
) -> None:
    conn = ensure_bouncer_buffer(db_path)
    conn.execute(
        """
        INSERT INTO rejection_log (created_at, client_ip, path, reason_code, detail, payload_preview)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            client_ip,
            path,
            reason_code,
            detail,
            payload_preview,
        ),
    )
    conn.close()


def record_reconciliation(
    *,
    trace_id: str,
    sku: str,
    ean: str,
    status: str,
    format_alert: str,
    shop_floor_action: str,
    payload: dict[str, Any],
    db_path: str = BOUNCER_DB_PATH,
) -> None:
    conn = ensure_bouncer_buffer(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO reconciliation_log
        (trace_id, created_at, sku, ean, status, format_alert, shop_floor_action, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            trace_id,
            datetime.now(timezone.utc).isoformat(),
            sku,
            ean,
            status,
            format_alert,
            shop_floor_action,
            json.dumps(payload),
        ),
    )
    conn.close()


def list_rejections(limit: int = 50, db_path: str = BOUNCER_DB_PATH) -> list[dict[str, Any]]:
    conn = ensure_bouncer_buffer(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, client_ip, path, reason_code, detail, payload_preview
            FROM rejection_log
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_reconciliation_by_trace_id(
    trace_id: str, db_path: str = BOUNCER_DB_PATH
) -> dict[str, Any] | None:
    """Return a stored reconciliation row (with parsed payload) or None."""
    conn = ensure_bouncer_buffer(db_path)
    try:
        row = conn.execute(
            """
            SELECT trace_id, created_at, sku, ean, status, format_alert, shop_floor_action, payload_json
            FROM reconciliation_log
            WHERE trace_id = ?;
            """,
            (trace_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        try:
            item["payload"] = json.loads(item.pop("payload_json", "{}"))
        except json.JSONDecodeError:
            item["payload"] = {}
        return item
    finally:
        conn.close()


def list_reconciliations(limit: int = 50, db_path: str = BOUNCER_DB_PATH) -> list[dict[str, Any]]:
    conn = ensure_bouncer_buffer(db_path)
    try:
        rows = conn.execute(
            """
            SELECT trace_id, created_at, sku, ean, status, format_alert, shop_floor_action, payload_json
            FROM reconciliation_log
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json", "{}"))
            except json.JSONDecodeError:
                item["payload"] = {}
            out.append(item)
        return out
    finally:
        conn.close()


def purge_reconciliation_log(db_path: str = BOUNCER_DB_PATH) -> int:
    """Delete all rows from the reconciliation ledger. Returns rows removed."""
    conn = ensure_bouncer_buffer(db_path)
    try:
        cursor = conn.execute("DELETE FROM reconciliation_log;")
        conn.commit()
        return int(cursor.rowcount if cursor.rowcount is not None else 0)
    finally:
        conn.close()


def count_rejections_since(since_iso: str, db_path: str = BOUNCER_DB_PATH) -> int:
    conn = ensure_bouncer_buffer(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM rejection_log WHERE created_at >= ?;",
            (since_iso,),
        ).fetchone()
        return int(row["c"]) if row else 0
    finally:
        conn.close()
