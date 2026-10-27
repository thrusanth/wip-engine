"""Edge camera live-feed telemetry: per-capture confidence, routing status and frame thumbnails.

Every Luna classification that reaches the API Bouncer (``/api/cv/damage-event``) — accepted or
rejected — is appended here so the dashboard can show the edge_camera.py test feed live.
Rows share the bouncer WAL database (``bouncer_audit.db``).
"""

from __future__ import annotations

import base64
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.bouncer_buffer import BOUNCER_DB_PATH, _connect
from services.product_lookup import case_size_for_catalog_key

MAX_FEED_ROWS = 200
# Middleware rejects bodies over 65,536 bytes; keep the thumbnail comfortably below that.
MAX_THUMBNAIL_B64_CHARS = 45_000

ROUTING_INTACT_SYNC = "INTACT_SYNC"
ROUTING_DAMAGED_REPRICE = "DAMAGED_REPRICE"
ROUTING_DAMAGED_WRITEOFF = "DAMAGED_WRITEOFF"
ROUTING_REJECTED = "REJECTED"
ROUTING_OTHER = "OTHER"


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS edge_feed_log (
            trace_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            catalog_key TEXT,
            item_name TEXT,
            raw_condition TEXT NOT NULL,
            effective_condition TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            confidence_threshold REAL NOT NULL,
            case_size INTEGER,
            expected_format TEXT,
            routing TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT,
            calculated_unit_price REAL,
            label_printed INTEGER NOT NULL DEFAULT 0,
            frame_b64 TEXT
        );
        """
    )
    # Tables created before case_size existed (they also still carry unused loose/phantom
    # columns with defaults, which new inserts simply leave at 0).
    columns = {row[1] for row in conn.execute("PRAGMA table_info(edge_feed_log);")}
    if "case_size" not in columns:
        conn.execute("ALTER TABLE edge_feed_log ADD COLUMN case_size INTEGER;")


def make_thumbnail_b64(
    image: str | bytes,
    *,
    max_edge: int = 512,
    max_b64_chars: int = MAX_THUMBNAIL_B64_CHARS,
) -> str:
    """Downscale a base64/bytes image to a JPEG thumbnail that fits the bouncer body limit."""
    from PIL import Image  # local import: only needed where frames are handled

    raw = base64.b64decode(image) if isinstance(image, str) else image
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    edge = max_edge
    quality = 70
    while True:
        work = img.copy()
        work.thumbnail((edge, edge))
        buf = io.BytesIO()
        work.save(buf, format="JPEG", quality=quality, optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        if len(encoded) <= max_b64_chars or edge <= 160:
            return encoded
        edge = int(edge * 0.8)
        quality = max(40, quality - 5)


def routing_from_result(
    *, status: str, transaction_type: Optional[str], rejected: bool
) -> str:
    if rejected:
        return ROUTING_REJECTED
    if status == "SYNCED":
        return ROUTING_INTACT_SYNC
    if transaction_type == "BOM_DECOMPOSITION_WITH_PRICING":
        return ROUTING_DAMAGED_REPRICE
    if transaction_type == "HEALTH_AND_SAFETY_WRITEOFF":
        return ROUTING_DAMAGED_WRITEOFF
    return ROUTING_OTHER


def record_feed_event(
    *,
    source: str,
    catalog_key: Optional[str],
    item_name: str,
    raw_condition: str,
    effective_condition: str,
    confidence_score: float,
    confidence_threshold: float,
    case_size: Optional[int],
    expected_format: Optional[str],
    routing: str,
    status: str,
    detail: Optional[str] = None,
    calculated_unit_price: Optional[float] = None,
    label_printed: bool = False,
    frame_b64: Optional[str] = None,
    trace_id: Optional[str] = None,
    db_path: str = BOUNCER_DB_PATH,
) -> str:
    trace = trace_id or f"FEED-{uuid.uuid4().hex[:10].upper()}"
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO edge_feed_log
            (trace_id, created_at, source, catalog_key, item_name, raw_condition,
             effective_condition, confidence_score, confidence_threshold,
             case_size, expected_format, routing, status,
             detail, calculated_unit_price, label_printed, frame_b64)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                trace,
                datetime.now(timezone.utc).isoformat(),
                source,
                catalog_key,
                item_name,
                raw_condition,
                effective_condition,
                float(confidence_score),
                float(confidence_threshold),
                int(case_size) if case_size is not None else None,
                expected_format,
                routing,
                status,
                detail,
                calculated_unit_price,
                1 if label_printed else 0,
                frame_b64,
            ),
        )
        conn.execute(
            """
            DELETE FROM edge_feed_log WHERE trace_id NOT IN (
                SELECT trace_id FROM edge_feed_log ORDER BY created_at DESC LIMIT ?
            );
            """,
            (MAX_FEED_ROWS,),
        )
    finally:
        conn.close()
    return trace


def list_feed_events(
    limit: int = 25, db_path: str = BOUNCER_DB_PATH
) -> list[dict[str, Any]]:
    """Newest-first events WITHOUT frame blobs (frames are served separately)."""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        rows = conn.execute(
            """
            SELECT trace_id, created_at, source, catalog_key, item_name, raw_condition,
                   effective_condition, confidence_score, confidence_threshold,
                   case_size, expected_format, routing, status,
                   detail, calculated_unit_price, label_printed,
                   (frame_b64 IS NOT NULL AND frame_b64 != '') AS has_frame
            FROM edge_feed_log
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (max(1, min(int(limit), MAX_FEED_ROWS)),),
        ).fetchall()
        events = [dict(row) for row in rows]
    finally:
        conn.close()
    for event in events:
        event["label_printed"] = bool(event["label_printed"])
        event["has_frame"] = bool(event["has_frame"])
        if event.get("case_size") is None:  # rows logged before case_size was stored
            event["case_size"] = case_size_for_catalog_key(event.get("catalog_key"))
    return events


def latest_frame(db_path: str = BOUNCER_DB_PATH) -> Optional[dict[str, Any]]:
    """Most recent event that carries a frame thumbnail, including the JPEG (base64)."""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        row = conn.execute(
            """
            SELECT trace_id, created_at, frame_b64
            FROM edge_feed_log
            WHERE frame_b64 IS NOT NULL AND frame_b64 != ''
            ORDER BY created_at DESC
            LIMIT 1;
            """
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def summarize_feed(events: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(events)
    intact = sum(1 for e in events if e["routing"] == ROUTING_INTACT_SYNC)
    damaged = sum(
        1
        for e in events
        if e["routing"] in (ROUTING_DAMAGED_REPRICE, ROUTING_DAMAGED_WRITEOFF)
    )
    rejected = sum(1 for e in events if e["routing"] == ROUTING_REJECTED)
    scores = [float(e["confidence_score"]) for e in events]
    return {
        "captures": total,
        "intact": intact,
        "damaged": damaged,
        "rejected": rejected,
        "avg_confidence": round(sum(scores) / total, 3) if total else None,
    }


def purge_feed(db_path: str = BOUNCER_DB_PATH) -> int:
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        cur = conn.execute("DELETE FROM edge_feed_log;")
        return cur.rowcount if cur.rowcount is not None else 0
    finally:
        conn.close()