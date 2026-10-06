"""
Offline telemetry buffer — append-only persistence for disconnected edge detections.

Detections are written to a local SQLite database running in WAL mode so concurrent
writers (rapid shelf scans) do not corrupt the on-device log before cloud sync resumes.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from models.schemas import OfflineDetectionEvent

DEFAULT_TELEMETRY_BUFFER_PATH = os.getenv(
    "TELEMETRY_BUFFER_PATH", "offline_detection_buffer.db"
)


class TelemetryBuffer:
    """
    WAL-backed SQLite store for ``OfflineDetectionEvent`` rows captured offline.

    PRAGMA ``journal_mode=WAL`` is applied on every connection so readers and writers
    can overlap safely during blackout operation.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path or DEFAULT_TELEMETRY_BUFFER_PATH)
        self._connection: Optional[sqlite3.Connection] = None

    @property
    def db_path(self) -> Path:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        """Open (or reuse) the SQLite connection with WAL journaling enabled."""
        if self._connection is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self._db_path, isolation_level=None)
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA busy_timeout=5000;")
            self._ensure_schema(self._connection)
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS offline_detection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                detected_quantity INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            """
        )

    def log_offline_detection(self, event: OfflineDetectionEvent) -> None:
        """
        Append a single offline detection row (insert-only; no updates or deletes).

        Intended for invocation while the edge stack operates in disconnected autonomy.
        """
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO offline_detection_log (timestamp, sku_id, detected_quantity, status)
            VALUES (?, ?, ?, ?);
            """,
            (
                event.timestamp,
                event.sku_id,
                event.detected_quantity,
                event.status,
            ),
        )
